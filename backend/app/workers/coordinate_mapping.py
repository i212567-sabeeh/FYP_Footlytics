"""Stream current tracks into metres without decoding or rerunning CV stages."""

import logging
import time
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.cv.coordinate_pipeline import CoordinateMappingError, map_tracking
from app.cv.player_position import PITCH_TOLERANCE_METRES
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.schemas.coordinates import CoordinateSummary
from app.services.coordinate_artifacts import CoordinateArtifact
from app.services.coordinate_inputs import CoordinateInputs, current_mapping_inputs
from app.services.domain_common import DomainError
from app.services.tracking_inputs import file_version
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def map_coordinates(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.COORDINATE_MAPPING,
                status=JobStatus.RUNNING,
                current_stage="loading_tracking",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _map(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Coordinate mapping attempt %s/%s was superseded",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception(
                    "Coordinate mapping failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, CoordinateMappingError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Coordinate mapping failed. "
                    "Check worker logs and output storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(
    session: Session, job_id: int, attempt: int, settings: Settings
) -> CoordinateInputs:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.attempt != attempt or job.status != JobStatus.RUNNING:
        raise SupersededAttempt
    match = session.get(Match, job.match_id)
    if match is None or match.is_archived or not match.club.is_active:
        raise DomainError(
            409, "Coordinate mapping requires an unarchived match in an active club."
        )
    inputs = current_mapping_inputs(session, match, settings)
    if (
        inputs.source.video.id != job.video_id
        or inputs.source.version != job.tracking_snapshot
        or inputs.calibration != job.calibration_snapshot
    ):
        raise DomainError(
            409,
            "The video, tracking result or calibration changed. "
            "Retry with current inputs.",
        )
    return inputs


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _map(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    inputs = _inputs(session, job_id, attempt, settings)
    source, calibration = inputs.source, inputs.calibration
    match_id, video_id = source.video.match_id, source.video.id
    assert source.tracking is not None
    session.commit()  # CSV work holds no database transaction.
    _running(session, job_id, attempt, current_stage="mapping_coordinates")
    last_percent, last_update = -5, time.monotonic()

    def progress(processed: int, total: int) -> None:
        nonlocal last_percent, last_update
        percent, now = min(99, int(100 * processed / total)), time.monotonic()
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(session, job_id, attempt, progress_percent=percent)
            last_percent, last_update = percent, now

    with CoordinateArtifact(settings, match_id, video_id, job_id, attempt) as artifact:
        run = map_tracking(
            source.path,
            source.detection,
            source.tracking,
            source.video.duration_seconds,
            calibration["homography_matrix"],
            calibration["pitch_length_metres"],
            calibration["pitch_width_metres"],
            write_position=artifact.write_position,
            progress=progress,
        )
        summary = CoordinateSummary(
            **asdict(run),
            tracking_job_id=source.job.id,
            tracking_attempt=source.job.attempt,
            calibration_id=calibration["id"],
            calibration_updated_at=calibration["updated_at"],
            pitch_length_metres=calibration["pitch_length_metres"],
            pitch_width_metres=calibration["pitch_width_metres"],
            bounds_tolerance_metres=PITCH_TOLERANCE_METRES,
        )
        _running(session, job_id, attempt, current_stage="saving_coordinates")
        # The existing match lock serializes upstream edits and job publication.
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, attempt, settings)
        relative = artifact.publish()
        # Also reject a filesystem edit during flush/rename; uncommitted output
        # remains private and the artifact context removes it on any failure.
        _inputs(session, job_id, attempt, settings)
        output = {
            **summary.model_dump(mode="json"),
            "artifact_version": file_version(artifact.path),
        }
        warnings = []
        if run.skipped_invalid_boxes:
            warnings.append(
                f"Skipped {run.skipped_invalid_boxes} malformed bounding boxes."
            )
        if not run.valid_mapped_rows:
            warnings.append("No valid tracked ground points were available to map.")
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
            coordinate_summary=output,
            artifact_relative_path=relative,
            warning_message=" ".join(warnings) or None,
        )
        artifact.keep()
    logger.info(
        "Coordinate job %s completed: %s mapped rows", job_id, run.valid_mapped_rows
    )
