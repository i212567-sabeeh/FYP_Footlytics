"""Queued visible-team geometry from exact cleaned trajectories and assignments."""

import logging
import time
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.analytics.team import calculate_teams
from app.analytics.team_rows import ordered_snapshots
from app.analytics.trajectory_rows import AnalyticsError, read_trajectories
from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.schemas.team_analytics import TacticsSummary
from app.services.domain_common import DomainError
from app.services.tactics_artifacts import TacticsArtifacts
from app.services.tactics_inputs import TacticsInputs, current_tactics_inputs
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def analyze_teams(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.TEAM_TACTICAL_ANALYTICS,
                status=JobStatus.RUNNING,
                current_stage="loading_assignments",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _analyze(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Tactical analytics attempt %s/%s superseded",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception(
                    "Team tactical analytics failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, AnalyticsError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Team tactical analytics failed. "
                    "Check worker logs and storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(
    session: Session, job_id: int, attempt: int, settings: Settings
) -> TacticsInputs:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.attempt != attempt or job.status != JobStatus.RUNNING:
        raise SupersededAttempt
    match = session.get(Match, job.match_id)
    if match is None or match.is_archived or not match.club.is_active:
        raise DomainError(409, "Team analytics requires an active club and match.")
    source = current_tactics_inputs(session, match, settings)
    if (
        source.trajectories.job.video_id != job.video_id
        or source.trajectories.version != job.trajectory_snapshot
        or source.assignment_version != job.assignment_snapshot
    ):
        raise DomainError(
            409,
            "Cleaned trajectories or effective team assignments changed. "
            "Retry with current inputs.",
        )
    return source


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _analyze(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    inputs = _inputs(session, job_id, attempt, settings)
    source = inputs.trajectories
    match_id, video_id = source.job.match_id, source.job.video_id
    source_id, source_attempt = source.job.id, source.job.attempt
    session.commit()
    last_percent, last_update = -5, time.monotonic()

    def progress(stage: str, done: int, total: int) -> None:
        nonlocal last_percent, last_update
        start, span = (0, 40) if stage == "ordering_snapshots" else (40, 59)
        percent = start + int(span * done / total) if total else start
        now = time.monotonic()
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(
                session,
                job_id,
                attempt,
                current_stage=stage,
                progress_percent=min(99, percent),
            )
            last_percent, last_update = percent, now

    with TacticsArtifacts(settings, match_id, video_id, job_id, attempt) as artifacts:
        # Scratch files are removed before atomic publication of the two CSVs.
        with (
            TemporaryDirectory(prefix="snapshots-", dir=artifacts.temporary) as scratch,
            closing(
                read_trajectories(
                    source.path,
                    source.summary,
                    source.decoded_frames,
                    source.frame_stride,
                    source.duration,
                )
            ) as rows,
            closing(
                ordered_snapshots(
                    rows,
                    Path(scratch),
                    source.summary.source_rows,
                    lambda n, total: progress("ordering_snapshots", n, total),
                )
            ) as ordered,
        ):
            run = calculate_teams(
                ordered,
                inputs.assignments,
                settings.tactics_min_players_per_team,
                source.summary.usable_rows,
                write=artifacts.write,
                progress=lambda n, total: progress("processing_snapshots", n, total),
            )
        summary = TacticsSummary(
            source_rows=source.summary.source_rows,
            usable_rows=source.summary.usable_rows,
            rejected_rows=source.summary.rejected_rows,
            assigned_rows=run.assigned_rows,
            unknown_rows=run.unknown_rows,
            observed_frames=run.observed_frames,
            trajectory_job_id=source_id,
            trajectory_attempt=source_attempt,
            pitch_length_metres=source.summary.pitch_length_metres,
            pitch_width_metres=source.summary.pitch_width_metres,
            min_players_per_team=settings.tactics_min_players_per_team,
        )
        _running(session, job_id, attempt, current_stage="saving_tactical_analytics")
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, attempt, settings)
        relative = artifacts.publish()
        _inputs(session, job_id, attempt, settings)
        warnings = []
        for team in run.teams:
            if not team.valid_snapshots:
                warnings.append(
                    f"{team.team}: insufficient visible players; "
                    "team geometry is unavailable."
                )
            elif team.insufficient_snapshots:
                warnings.append(
                    f"{team.team}: {team.insufficient_snapshots} insufficient "
                    "snapshots excluded from averages."
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
            tactics_summary={
                **summary.model_dump(mode="json"),
                "artifact_versions": artifacts.versions(),
            },
            artifact_relative_path=relative,
            warning_message=" ".join(warnings) or None,
        )
        artifacts.keep()
