"""Reopen and verify the stored source without performing football analysis."""

import logging
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.jobs import JobStatus, JobType
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.media import MatchVideo, ProcessingJob
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService
from app.services.video_inspection import inspect_video
from app.workers.state import fail as _fail
from app.workers.state import transition as _transition

logger = logging.getLogger(__name__)


def prepare_video(processing_job_id: int, attempt: int) -> None:
    """RQ entrypoint: identifiers only; this process owns its database resources.

    Percentages denote verified preparation milestones, not frames analyzed:
    claimed (10), source exists (25), metadata/frame verified (80), saved (100).
    Conditional claims make duplicate and stale retry deliveries harmless.
    """
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not _transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.VIDEO_PREPARATION,
                status=JobStatus.RUNNING,
                current_stage="checking_source",
                progress_percent=10,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            logger.info("Worker started processing job %s", processing_job_id)
            try:
                _prepare(session, processing_job_id, attempt, settings)
            except Exception as error:
                safe_message = (
                    error.detail
                    if isinstance(error, DomainError)
                    else (
                        "Video preparation failed. Retry, or contact an "
                        "administrator if it continues."
                    )
                )
                logger.exception(
                    "Video preparation failed for job %s", processing_job_id
                )
                _fail(session, processing_job_id, attempt, safe_message)
                raise
    finally:
        engine.dispose()


def _prepare(session: Session, job_id: int, attempt: int, settings) -> None:
    job = session.get(ProcessingJob, job_id)
    assert job is not None
    video = session.get(MatchVideo, job.video_id)
    if video is None or not video.is_active or video.match_id != job.match_id:
        raise DomainError(
            409, "The source video was replaced or is no longer available."
        )
    video_id, expected_size = video.id, video.file_size_bytes
    path = StorageService(settings).resolve(video.relative_storage_path)
    session.commit()  # Release the read transaction before filesystem/decoder work.
    if not path.is_file():
        raise DomainError(422, "The stored source video is missing. Upload it again.")
    if path.stat().st_size != expected_size:
        raise DomainError(422, "The stored source video changed. Upload it again.")
    if not _transition(
        session,
        job_id,
        attempt,
        expected=(JobStatus.RUNNING,),
        current_stage="validating_video",
        progress_percent=25,
    ):
        return
    metadata = inspect_video(path, settings)
    if not _transition(
        session,
        job_id,
        attempt,
        expected=(JobStatus.RUNNING,),
        current_stage="saving_metadata",
        progress_percent=80,
    ):
        return
    # The active job blocks API replacement. Keep the row predicate as an extra
    # guard if a source is retired by a future internal maintenance operation.
    result = session.execute(
        update(MatchVideo)
        .where(MatchVideo.id == video_id, MatchVideo.is_active.is_(True))
        .values(**asdict(metadata), updated_at=utc_now())
    )
    if result.rowcount != 1:
        raise DomainError(409, "The source video was replaced during preparation.")
    status = (
        JobStatus.COMPLETED_WITH_WARNINGS
        if metadata.warning_message
        else JobStatus.COMPLETED
    )
    _transition(
        session,
        job_id,
        attempt,
        expected=(JobStatus.RUNNING,),
        status=status,
        current_stage="completed",
        progress_percent=100,
        finished_at=utc_now(),
        warning_message=metadata.warning_message,
        error_message=None,
    )
    logger.info("Processing job %s completed with status %s", job_id, status)


def _record_external_failure(job) -> None:
    """RQ timeout/worker-failure hook also creates its own database session."""
    job_id = job.kwargs.get("processing_job_id")
    attempt = job.kwargs.get("attempt")
    if not isinstance(job_id, int) or not isinstance(attempt, int):
        return
    engine = create_database_engine(get_settings().database_url)
    try:
        with create_session_factory(engine)() as session:
            _fail(
                session,
                job_id,
                attempt,
                "The processing worker stopped before completion. Retry the job.",
            )
    finally:
        engine.dispose()


def record_rq_failure(
    job, connection, exception_type, exception_value, traceback
) -> None:
    _record_external_failure(job)


def record_workhorse_failure(job, retpid, ret_val, rusage) -> None:
    _record_external_failure(job)
