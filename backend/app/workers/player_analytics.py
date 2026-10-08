"""Queued physical analytics from one exact cleaned trajectory result."""

import logging
import time
from contextlib import closing
from dataclasses import asdict

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.analytics.player import calculate_players
from app.analytics.trajectory_rows import AnalyticsError, read_trajectories
from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.schemas.player_analytics import AnalyticsSummary
from app.services.analytics_artifacts import AnalyticsArtifacts
from app.services.domain_common import DomainError
from app.services.trajectory_service import TrajectorySource, current_trajectories
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def analyze_players(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.PLAYER_ANALYTICS,
                status=JobStatus.RUNNING,
                current_stage="loading_trajectories",
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
                    "Player analytics attempt %s/%s superseded",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception(
                    "Player analytics failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, AnalyticsError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Player analytics failed. "
                    "Check worker logs and storage, then retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(
    session: Session, job_id: int, attempt: int, settings: Settings
) -> TrajectorySource:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    if job is None or job.attempt != attempt or job.status != JobStatus.RUNNING:
        raise SupersededAttempt
    match = session.get(Match, job.match_id)
    if match is None or match.is_archived or not match.club.is_active:
        raise DomainError(409, "Player analytics requires an active club and match.")
    source = current_trajectories(session, match, settings)
    if source.job.video_id != job.video_id or source.version != job.trajectory_snapshot:
        raise DomainError(
            409,
            "Cleaned trajectories or upstream inputs changed. "
            "Retry with current results.",
        )
    return source


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _analyze(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    source = _inputs(session, job_id, attempt, settings)
    match_id, video_id = source.job.match_id, source.job.video_id
    source_id, source_attempt = source.job.id, source.job.attempt
    session.commit()
    last_percent, last_update = -5, time.monotonic()

    def progress(processed: int, total: int) -> None:
        nonlocal last_percent, last_update
        percent = min(99, int(99 * processed / total)) if total else 0
        now = time.monotonic()
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(
                session,
                job_id,
                attempt,
                current_stage="calculating_player_analytics",
                progress_percent=percent,
            )
            last_percent, last_update = percent, now

    with AnalyticsArtifacts(settings, match_id, video_id, job_id, attempt) as artifacts:
        with closing(
            read_trajectories(
                source.path,
                source.summary,
                source.decoded_frames,
                source.frame_stride,
                source.duration,
            )
        ) as rows:
            run = calculate_players(
                rows, source.summary, settings, write=artifacts.write, progress=progress
            )
        summary = AnalyticsSummary(
            **asdict(run),
            trajectory_job_id=source_id,
            trajectory_attempt=source_attempt,
            pitch_length_metres=source.summary.pitch_length_metres,
            pitch_width_metres=source.summary.pitch_width_metres,
            sprint_speed_threshold_mps=settings.player_sprint_speed_threshold_mps,
            sprint_min_duration_seconds=settings.player_sprint_min_duration_seconds,
            max_plausible_speed_mps=source.summary.max_plausible_speed_mps,
            max_gap_seconds=source.summary.max_gap_seconds,
            heatmap_bins_x=settings.player_heatmap_bins_x,
            heatmap_bins_y=settings.player_heatmap_bins_y,
        )
        _running(session, job_id, attempt, current_stage="saving_analytics")
        session.execute(
            update(Match)
            .where(Match.id == match_id)
            .values(id=Match.id, updated_at=Match.updated_at)
        )
        _inputs(session, job_id, attempt, settings)
        relative = artifacts.publish()
        _inputs(session, job_id, attempt, settings)
        warnings = []
        if not run.valid_intervals:
            warnings.append(
                "No valid movement intervals were available; speeds are unavailable."
            )
        if run.excluded_intervals:
            warnings.append(
                f"Excluded {run.excluded_intervals} invalid movement intervals."
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
            analytics_summary={
                **summary.model_dump(mode="json"),
                "artifact_versions": artifacts.versions(),
            },
            artifact_relative_path=relative,
            warning_message=" ".join(warnings) or None,
        )
        artifacts.keep()
    logger.info(
        "Player analytics job %s completed: %s tracks", job_id, run.unique_tracks
    )
