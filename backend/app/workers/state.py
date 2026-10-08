"""Conditional state changes shared by preparation and detection attempts."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.jobs import ACTIVE_JOB_STATUSES, JobStatus
from app.database.base import utc_now
from app.models.media import ProcessingJob


def transition(
    session: Session,
    job_id: int,
    attempt: int,
    *,
    expected: tuple[str, ...],
    job_type: str | None = None,
    **values,
) -> bool:
    statement = update(ProcessingJob).where(
        ProcessingJob.id == job_id,
        ProcessingJob.attempt == attempt,
        ProcessingJob.status.in_(expected),
    )
    if job_type is not None:
        statement = statement.where(ProcessingJob.job_type == job_type)
    result = session.execute(
        statement.values(**values, updated_at=utc_now()).execution_options(
            synchronize_session=False
        )
    )
    session.commit()
    return result.rowcount == 1


def fail(session: Session, job_id: int, attempt: int, message: str) -> None:
    session.rollback()
    transition(
        session,
        job_id,
        attempt,
        expected=ACTIVE_JOB_STATUSES,
        status=JobStatus.FAILED,
        current_stage="failed",
        error_message=message,
        finished_at=utc_now(),
    )
