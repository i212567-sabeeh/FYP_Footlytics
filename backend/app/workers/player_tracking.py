"""ByteTrack consumes a completed detection artifact; it never runs a detector."""

import logging
import time
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.cv.tracker import ByteTrackTracker, TrackingError
from app.cv.tracking_pipeline import track_detections
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.schemas.detection import DetectionSummary
from app.services.detection_inputs import current_calibration, snapshot
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService
from app.services.tracking_artifacts import TrackingArtifact
from app.services.tracking_inputs import current_detection, file_version
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)
VIDEO_UNAVAILABLE = "The stored source video is missing or changed."
LOW_CONFIDENCE_UNAVAILABLE = (
    "Saved detections omit low-confidence boxes that ByteTrack uses to keep player "
    "IDs through occlusions. Run player detection again, then tracking."
)


class SupersededAttempt(Exception):
    pass


def _video_version(path: Path) -> dict[str, int]:
    # One curated failure whether the source disappears before or during tracking.
    try:
        return file_version(path)
    except OSError as error:
        raise TrackingError(VIDEO_UNAVAILABLE) from error


def track_players(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.PLAYER_TRACKING,
                status=JobStatus.RUNNING,
                current_stage="loading_detections",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _track(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Tracking attempt %s/%s is no longer active",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception("Player tracking failed for job %s", processing_job_id)
                message = (
                    str(error)
                    if isinstance(error, TrackingError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Player tracking failed. Check worker logs and output "
                    "storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(session: Session, job_id: int, settings: Settings):
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
            409, "Tracking requires an unarchived match in an active club."
        )
    calibration = snapshot(current_calibration(session, match, video))
    if calibration != job.calibration_snapshot:
        raise DomainError(
            409,
            "The calibration changed after tracking was queued. "
            "Run current detection first.",
        )
    detection, provenance = current_detection(
        session, match, video, calibration, settings
    )
    if provenance != job.detection_snapshot:
        raise DomainError(
            409,
            "The detection artifact changed after tracking was queued. "
            "Retry with current detections.",
        )
    return job, video, detection


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _track(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    job, video, detection = _inputs(session, job_id, settings)
    match_id, video_id = job.match_id, video.id
    source_id, source_attempt = detection.id, detection.attempt
    source_warning = detection.warning_message
    summary = DetectionSummary.model_validate(detection.detection_summary)
    storage = StorageService(settings)
    path = storage.resolve(detection.artifact_relative_path)
    video_path = storage.resolve(video.relative_storage_path)
    expected_video_size = video.file_size_bytes
    duration, fps = video.duration_seconds, video.fps
    session.commit()  # No database transaction spans CSV processing.
    video_version = _video_version(video_path)
    if video_version["size"] != expected_video_size:
        raise TrackingError(VIDEO_UNAVAILABLE)
    tracker = ByteTrackTracker(
        settings,
        match_id=match_id,
        image_width=summary.frame_width,
        image_height=summary.frame_height,
        frame_stride=summary.frame_stride,
    )
    # ByteTrack's second association uses boxes above TRACK_LOW_THRESH; older
    # artifacts stored only reported detections, so that stage had no input.
    low_confidence_association = (
        summary.stored_confidence_threshold <= settings.track_low_thresh
    )
    _running(session, job_id, attempt, current_stage="tracking_players")
    last_percent, last_update = -5, time.monotonic()

    def progress(processed: int, total: int) -> None:
        nonlocal last_percent, last_update
        percent, now = min(99, int(100 * processed / total)), time.monotonic()
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(session, job_id, attempt, progress_percent=percent)
            last_percent, last_update = percent, now

    with TrackingArtifact(settings, match_id, video_id, job_id, attempt) as artifact:
        run = track_detections(
            path,
            summary,
            tracker,
            duration=duration,
            write_frame=artifact.write_tracks,
            progress=progress,
        )
        _running(session, job_id, attempt, current_stage="saving_tracks")
        output = {
            **asdict(run),
            "frame_stride": summary.frame_stride,
            "frame_width": summary.frame_width,
            "frame_height": summary.frame_height,
            "detection_job_id": source_id,
            "detection_attempt": source_attempt,
            "tracker": "bytetrack",
            "artifact_format": "csv",
            "track_high_thresh": settings.track_high_thresh,
            "track_low_thresh": settings.track_low_thresh,
            "track_match_thresh": settings.track_match_thresh,
            "track_buffer": settings.track_buffer,
            "track_buffer_updates": tracker.track_buffer_updates,
            # Nominal lost-track memory: sampled updates x stride / source FPS.
            "track_buffer_seconds": tracker.track_buffer_updates
            * summary.frame_stride
            / fps,
            "low_confidence_association": low_confidence_association,
        }
        relative_path = artifact.publish()
        # Reuse the match lock shared by job creation, calibration and replacement.
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, settings)
        if (
            _video_version(storage.resolve(video.relative_storage_path))
            != video_version
        ):
            raise TrackingError("The stored source video changed during tracking.")
        warnings = [
            message
            for message in (
                source_warning,
                None if low_confidence_association else LOW_CONFIDENCE_UNAVAILABLE,
                "No confirmed player tracks were produced."
                if not run.total_track_rows
                else None,
            )
            if message
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
            tracking_summary=output,
            artifact_relative_path=relative_path,
            warning_message=" ".join(warnings) or None,
        )
        artifact.keep()
    logger.info(
        "Tracking job %s completed: %s frames, %s tracks",
        job_id,
        run.processed_frames,
        run.unique_tracks,
    )
