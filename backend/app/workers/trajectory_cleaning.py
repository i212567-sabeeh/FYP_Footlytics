"""Clean saved coordinates in a separate worker; never rerun upstream processing."""

import logging
import time
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.cv.coordinate_rows import TrajectoryError
from app.cv.trajectory_pipeline import clean_coordinates
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.schemas.trajectories import TrajectorySummary
from app.services.coordinate_service import CoordinateSource, current_coordinates
from app.services.domain_common import DomainError
from app.services.tracking_inputs import file_version
from app.services.trajectory_artifacts import TrajectoryArtifact
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def clean_trajectories(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.TRAJECTORY_CLEANING,
                status=JobStatus.RUNNING,
                current_stage="loading_coordinates",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _clean(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Trajectory attempt %s/%s superseded", processing_job_id, attempt
                )
            except Exception as error:
                logger.exception(
                    "Trajectory cleaning failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, TrajectoryError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Trajectory cleaning failed. "
                    "Check worker logs and storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(
    session: Session,
    job_id: int,
    attempt: int,
    settings: Settings,
) -> CoordinateSource:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.attempt != attempt or job.status != JobStatus.RUNNING:
        raise SupersededAttempt
    match = session.get(Match, job.match_id)
    if match is None or match.is_archived or not match.club.is_active:
        raise DomainError(409, "Trajectory cleaning requires an active club and match.")
    source = current_coordinates(session, match, settings)
    if source.job.video_id != job.video_id or source.version != job.coordinate_snapshot:
        raise DomainError(
            409,
            "Coordinates or their upstream inputs changed. Retry with current results.",
        )
    return source


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _clean(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    source = _inputs(session, job_id, attempt, settings)
    match_id, video_id = source.job.match_id, source.job.video_id
    source_id, source_attempt = source.job.id, source.job.attempt
    session.commit()
    last_percent, last_update, last_stage = -5, time.monotonic(), ""

    def progress(stage: str, processed: int, total: int) -> None:
        nonlocal last_percent, last_update, last_stage
        # Actual input rows read (0..40%), then actual rows cleaned/written (40..99%).
        percent = (
            0
            if not total
            else (
                int(40 * processed / total)
                if stage == "loading_coordinates"
                else min(99, 40 + int(59 * processed / total))
            )
        )
        now = time.monotonic()
        if stage != last_stage or percent >= last_percent + 5 or now - last_update >= 5:
            _running(
                session, job_id, attempt, current_stage=stage, progress_percent=percent
            )
            last_percent, last_update, last_stage = percent, now, stage

    with TrajectoryArtifact(settings, match_id, video_id, job_id, attempt) as artifact:
        run = clean_coordinates(
            source.path,
            source.summary,
            source.decoded_frames,
            source.frame_stride,
            source.duration,
            settings,
            artifact.path.parent,
            write_observation=artifact.write_observation,
            progress=progress,
        )
        summary = TrajectorySummary(
            **asdict(run),
            coordinate_job_id=source_id,
            coordinate_attempt=source_attempt,
            pitch_length_metres=source.summary.pitch_length_metres,
            pitch_width_metres=source.summary.pitch_width_metres,
            max_plausible_speed_mps=settings.trajectory_max_plausible_speed_mps,
            max_gap_seconds=settings.trajectory_max_gap_seconds,
            smoothing_window=settings.trajectory_smoothing_window,
            smoothing_max_shift_metres=settings.trajectory_smoothing_max_shift_metres,
        )
        _running(session, job_id, attempt, current_stage="writing_trajectories")
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, attempt, settings)
        relative = artifact.publish()
        _inputs(session, job_id, attempt, settings)
        warnings = []
        if run.rejected_rows:
            warnings.append(f"Retained {run.rejected_rows} unusable raw observations.")
        if not run.usable_rows:
            warnings.append("No usable trajectory observations were available.")
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
            trajectory_summary={
                **summary.model_dump(mode="json"),
                "artifact_version": file_version(artifact.path),
            },
            artifact_relative_path=relative,
            warning_message=" ".join(warnings) or None,
        )
        artifact.keep()
    logger.info("Trajectory job %s completed: %s usable rows", job_id, run.usable_rows)
