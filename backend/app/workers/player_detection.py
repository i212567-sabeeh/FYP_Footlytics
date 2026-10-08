"""Real, incremental YOLO detection on the existing durable job queue."""

import logging
import time
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.cv.detector import DetectionError, YoloPlayerDetector
from app.cv.pipeline import detect_video
from app.cv.roi import build_pitch_roi
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.services.detection_artifacts import DetectionArtifact
from app.services.detection_inputs import current_calibration, snapshot
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def detect_players(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.PLAYER_DETECTION,
                status=JobStatus.RUNNING,
                current_stage="loading_model",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _detect(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Detection attempt %s/%s is no longer active",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception(
                    "Player detection failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, DetectionError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Player detection failed. Check worker logs and output "
                    "storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                # RQ records this failure and keeps the worker available for later jobs.
                raise
    finally:
        engine.dispose()


def _inputs(session: Session, job_id: int):
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    assert job is not None
    match = session.get(Match, job.match_id)
    video = session.get(MatchVideo, job.video_id)
    if (
        match is None
        or video is None
        or not video.is_active
        or video.match_id != match.id
    ):
        raise DomainError(
            409, "The source video was replaced or is no longer available."
        )
    if match.is_archived or not match.club.is_active:
        raise DomainError(
            409, "Detection requires an unarchived match in an active club."
        )
    calibration = current_calibration(session, match, video)
    if snapshot(calibration) != job.calibration_snapshot:
        raise DomainError(
            409,
            "The calibration changed after this job was queued. "
            "Retry with the current calibration.",
        )
    return job, video, calibration


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _detect(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    job, video, calibration = _inputs(session, job_id)
    match_id, video_id = job.match_id, video.id
    width, height = calibration.image_width, calibration.image_height
    provenance = snapshot(calibration)
    path = StorageService(settings).resolve(video.relative_storage_path)
    expected_size = video.file_size_bytes
    roi = (
        build_pitch_roi(
            calibration.image_points,
            calibration.pitch_points,
            calibration.pitch_length_metres,
            calibration.pitch_width_metres,
            width,
            height,
        )
        if settings.detection_roi_enabled
        else None
    )
    roi_reason = (
        None
        if roi
        else (
            "ROI filtering is disabled in settings."
            if not settings.detection_roi_enabled
            else "Calibration does not contain a reliable complete "
            "four-corner pitch polygon."
        )
    )
    session.commit()  # Never hold a transaction across model download/inference.
    if not path.is_file() or path.stat().st_size != expected_size:
        raise DetectionError(
            "The stored source video is missing or changed. Upload it again."
        )
    detector = YoloPlayerDetector(settings)
    _running(session, job_id, attempt, current_stage="detecting_players")
    last_percent, last_update = -5, time.monotonic()

    def progress(decoded: int, total: int | None) -> None:
        nonlocal last_percent, last_update
        percent = min(99, int(100 * decoded / total)) if total else 0
        now = time.monotonic()
        # At most one update per 5% or five seconds, also checking retry ownership.
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(session, job_id, attempt, progress_percent=percent)
            last_percent, last_update = percent, now

    with DetectionArtifact(settings, match_id, video_id, job_id, attempt) as artifact:
        run = detect_video(
            path,
            detector,
            stride=settings.detection_frame_stride,
            image_width=width,
            image_height=height,
            roi=roi,
            confidence_threshold=settings.yolo_confidence,
            write_frame=artifact.write_frame,
            progress=progress,
        )
        _running(session, job_id, attempt, current_stage="saving_detections")
        summary = {
            **asdict(run),
            "average_detections_per_processed_frame": run.total_detections
            / run.processed_frames,
            "frame_stride": settings.detection_frame_stride,
            "frame_width": width,
            "frame_height": height,
            "model": detector.model_name,
            "device": detector.device,
            "confidence_threshold": settings.yolo_confidence,
            "candidate_confidence_threshold": settings.detection_candidate_confidence,
            "inference_image_size": settings.yolo_image_size,
            "roi_filter_applied": roi is not None,
            "roi_skip_reason": roi_reason,
            "calibration_id": provenance["id"],
            "calibration_updated_at": provenance["updated_at"],
            "artifact_format": "csv",
        }
        relative_path = artifact.publish()
        # The same Match lock used by calibration/video writes makes validation
        # and final job publication atomic with respect to those mutations.
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id)
        if not path.is_file() or path.stat().st_size != expected_size:
            raise DetectionError("The stored source video changed during detection.")
        warnings = [
            text
            for text in (
                roi_reason,
                "Nominal-FPS timestamps were used for some sampled frames."
                if run.timestamp_fallback_frames
                else None,
            )
            if text
        ]
        _running(
            session,
            job_id,
            attempt,
            status=JobStatus.COMPLETED_WITH_WARNINGS
            if warnings
            else JobStatus.COMPLETED,
            current_stage="completed",
            progress_percent=100,
            finished_at=utc_now(),
            detection_summary=summary,
            artifact_relative_path=relative_path,
            warning_message=" ".join(warnings) or None,
        )
        artifact.keep()
    logger.info(
        "Detection job %s completed: %s frames, %s person candidates",
        job_id,
        run.processed_frames,
        run.total_detections,
    )
