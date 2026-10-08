"""Queued, read-only presentation of current saved analytics."""

import logging

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.models.user import User
from app.reports.builder import build_report
from app.reports.data import load_report_data
from app.schemas.reports import ReportSummary
from app.services.domain_common import DomainError
from app.services.report_artifacts import ReportArtifact, validate_pdf
from app.services.report_inputs import ReportInputs, capture_inputs
from app.services.tracking_inputs import file_version
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session,
        job_id,
        attempt,
        expected=(JobStatus.RUNNING,),
        job_type=JobType.MATCH_REPORT,
        **values,
    ):
        raise SupersededAttempt


def _inputs(
    session: Session, job_id: int, attempt: int, settings: Settings
) -> tuple[ReportInputs, User]:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.attempt != attempt or job.status != JobStatus.RUNNING:
        raise SupersededAttempt
    match = session.get(Match, job.match_id)
    user = session.get(User, job.created_by_user_id)
    if match is None or match.is_archived or not match.club.is_active or user is None:
        raise DomainError(
            409, "Report generation requires an active club, match and account."
        )
    inputs = capture_inputs(session, user, job.match_id, settings)
    if inputs.video_id != job.video_id or inputs.snapshot != job.report_snapshot:
        raise DomainError(
            409,
            "Report inputs changed. "
            "Retry with current analytics and match information.",
        )
    return inputs, user


def _generate(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    inputs, user = _inputs(session, job_id, attempt, settings)
    match_id, video_id = inputs.metadata["match_id"], inputs.video_id
    assert video_id is not None
    _running(
        session, job_id, attempt, current_stage="reading_analytics", progress_percent=10
    )
    data = load_report_data(
        inputs,
        utc_now(),
        session,
        user,
        settings,
        lambda done, total: _running(
            session,
            job_id,
            attempt,
            current_stage="reading_heatmaps",
            progress_percent=10 + int(30 * done / total),
        ),
    )
    with ReportArtifact(settings, match_id, video_id, job_id, attempt) as artifact:
        _running(
            session, job_id, attempt, current_stage="building_pdf", progress_percent=45
        )
        sections = build_report(data, artifact.temporary)
        _running(
            session,
            job_id,
            attempt,
            current_stage="validating_pdf",
            progress_percent=85,
        )
        pages, size = validate_pdf(artifact.temporary)
        summary = ReportSummary(
            generated_at=data.generated_at,
            page_count=pages,
            size_bytes=size,
            player_rows=len(data.players or []),
            team_rows=len(data.teams or []),
            heatmaps=len(data.heatmaps),
            sections=sections,
        )
        _running(
            session,
            job_id,
            attempt,
            current_stage="publishing_report",
            progress_percent=95,
        )
        # Replacement, assignment correction, retries and publication share this lock.
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, attempt, settings)
        relative = artifact.publish()
        _inputs(session, job_id, attempt, settings)
        warnings = (
            "Some analytics or team assignments are unavailable; see the report."
            if inputs.unavailable
            else None
        )
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
            report_summary={
                **summary.model_dump(mode="json"),
                "artifact_version": file_version(artifact.path),
            },
            artifact_relative_path=relative,
            warning_message=warnings,
        )
        artifact.keep()


def generate_report(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.MATCH_REPORT,
                status=JobStatus.RUNNING,
                current_stage="loading_report_inputs",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _generate(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Report attempt %s/%s superseded", processing_job_id, attempt
                )
            except Exception as error:
                logger.exception("Match report failed for job %s", processing_job_id)
                message = (
                    error.detail
                    if isinstance(error, DomainError)
                    else "Report generation failed. "
                    "Check worker logs and storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()
