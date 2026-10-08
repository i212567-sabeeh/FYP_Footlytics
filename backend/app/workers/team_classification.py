"""Classify saved tracks without rerunning YOLO or ByteTrack."""

import logging
import time

import cv2
import numpy as np
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.jobs import JobStatus, JobType
from app.core.teams import TrackTeam
from app.cv.team_classifier import Appearance
from app.cv.team_pipeline import (
    ClassificationError,
    ClassificationRun,
    classify_tracking,
)
from app.database.base import utc_now
from app.database.session import create_database_engine, create_session_factory
from app.models.football import Match
from app.models.media import ProcessingJob
from app.models.team_assignment import TrackTeamAssignment
from app.services.domain_common import DomainError
from app.services.frame_service import extract_frame
from app.services.result_inputs import ResultSource, current_result
from app.services.team_assignment_service import assignment_query, tracking_version
from app.services.team_color_service import color_snapshot
from app.workers.state import fail, transition

logger = logging.getLogger(__name__)


class SupersededAttempt(Exception):
    pass


def classify_teams(processing_job_id: int, attempt: int) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine)() as session:
            if not transition(
                session,
                processing_job_id,
                attempt,
                expected=(JobStatus.QUEUED,),
                job_type=JobType.TEAM_CLASSIFICATION,
                status=JobStatus.RUNNING,
                current_stage="loading_tracks",
                progress_percent=0,
                started_at=utc_now(),
                finished_at=None,
                error_message=None,
            ):
                return
            try:
                _classify(session, processing_job_id, attempt, settings)
            except SupersededAttempt:
                session.rollback()
                logger.info(
                    "Classification attempt %s/%s was superseded",
                    processing_job_id,
                    attempt,
                )
            except Exception as error:
                logger.exception(
                    "Team classification failed for job %s", processing_job_id
                )
                message = (
                    str(error)
                    if isinstance(error, ClassificationError)
                    else error.detail
                    if isinstance(error, DomainError)
                    else "Team classification failed. Check worker logs and retry."
                )
                fail(session, processing_job_id, attempt, message)
                raise
    finally:
        engine.dispose()


def _inputs(session: Session, job_id: int, settings: Settings) -> ResultSource:
    session.expire_all()
    job = session.get(ProcessingJob, job_id)
    assert job is not None
    match = session.get(Match, job.match_id)
    if match is None or match.is_archived or not match.club.is_active:
        raise DomainError(
            409, "Team classification requires an unarchived match in an active club."
        )
    source = current_result(session, match, "tracking", settings)
    if source.video.id != job.video_id or source.version != job.tracking_snapshot:
        raise DomainError(
            409, "Video or tracking inputs changed. Retry with current tracks."
        )
    if color_snapshot(session, match.id, source.version) != job.team_color_snapshot:
        raise DomainError(
            409,
            "Team-color prototypes changed. "
            "Retry classification with the current examples.",
        )
    return source


def _running(session: Session, job_id: int, attempt: int, **values) -> None:
    if not transition(
        session, job_id, attempt, expected=(JobStatus.RUNNING,), **values
    ):
        raise SupersededAttempt


def _classify(session: Session, job_id: int, attempt: int, settings: Settings) -> None:
    source = _inputs(session, job_id, settings)
    colors = session.get(ProcessingJob, job_id).team_color_snapshot
    prototypes = (
        {
            TrackTeam(p["team"]): Appearance(tuple(p["color"]), p["quality"])
            for p in colors["prototypes"]
        }
        if colors
        else None
    )
    session.commit()  # No transaction spans frame decoding or color extraction.
    _running(session, job_id, attempt, current_stage="sampling_jerseys")
    last_percent, last_update = -5, time.monotonic()

    def progress(processed: int, total: int) -> None:
        nonlocal last_percent, last_update
        percent, now = min(99, int(100 * processed / total)), time.monotonic()
        if percent >= last_percent + 5 or now - last_update >= 5:
            _running(session, job_id, attempt, progress_percent=percent)
            last_percent, last_update = percent, now

    def load_frame(number: int):
        frame = extract_frame(source.video, 0, settings, frame_number=number)
        return cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)

    assert source.tracking is not None
    run = classify_tracking(
        source.path,
        source.detection,
        source.tracking,
        source.video.duration_seconds,
        settings,
        load_frame=load_frame,
        progress=progress,
        prototypes=prototypes,
    )
    _running(session, job_id, attempt, current_stage="saving_team_assignments")
    _publish(session, job_id, attempt, source, run, settings)
    logger.info(
        "Classification job %s completed: %s tracks", job_id, len(run.predictions)
    )


def _publish(
    session: Session,
    job_id: int,
    attempt: int,
    source: ResultSource,
    run: ClassificationRun,
    settings: Settings,
) -> None:
    match_id = source.video.match_id
    session.execute(
        update(Match)
        .where(Match.id == match_id)
        .values(id=Match.id, updated_at=Match.updated_at)
    )
    _inputs(session, job_id, settings)
    colors = session.get(ProcessingJob, job_id).team_color_snapshot
    mode = "user_seeded" if colors else "automatic"
    counts = {team: sum(p.team == team for p in run.predictions) for team in TrackTeam}
    warning = (
        "No tracked players are available for team classification."
        if not run.predictions
        else "Some tracks have weak jersey evidence; their automatic team is Unknown."
        if counts[TrackTeam.UNKNOWN]
        else None
    )
    output = {
        "tracking_job_id": source.job.id,
        "tracking_attempt": source.job.attempt,
        "processed_frames": run.processed_frames,
        "sampled_frames": run.sampled_frames,
        "valid_samples": run.valid_samples,
        "total_tracks": len(run.predictions),
        "team_a_tracks": counts[TrackTeam.TEAM_A],
        "team_b_tracks": counts[TrackTeam.TEAM_B],
        "unknown_tracks": counts[TrackTeam.UNKNOWN],
        "sample_interval": settings.team_sample_interval,
        "sampling_method": "uniform_valid_candidates_v2",
        "max_samples_per_track": settings.team_max_samples_per_track,
        "min_samples": settings.team_min_samples,
        "min_crop_width": settings.team_min_crop_width,
        "min_crop_height": settings.team_min_crop_height,
        "unknown_threshold": settings.team_unknown_threshold,
        "method": "median_lab_kmeans_v1",
        "mapping": "user_selected_team_colors" if colors else "ascending_lab_centroid",
        "classification_mode": mode,
        "prototype_set_id": colors["id"] if colors else None,
        "diagnostics": run.diagnostics or None,
    }
    # Unlike progress transitions, final state and assignments must commit together.
    # Conditional ownership is checked BEFORE writes; a superseded attempt rolls
    # back instead of publishing partially updated assignments.
    result = session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.attempt == attempt,
            ProcessingJob.status == JobStatus.RUNNING,
            ProcessingJob.job_type == JobType.TEAM_CLASSIFICATION,
        )
        .values(
            status=JobStatus.COMPLETED_WITH_WARNINGS
            if warning
            else JobStatus.COMPLETED,
            current_stage="completed",
            progress_percent=100,
            finished_at=utc_now(),
            updated_at=utc_now(),
            classification_summary=output,
            warning_message=warning,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise SupersededAttempt
    version = tracking_version(source.version)
    existing = {
        row.track_id: row
        for row in session.scalars(assignment_query(match_id, version))
    }
    for prediction in run.predictions:
        assignment = existing.get(prediction.track_id)
        if assignment is None:
            assignment = TrackTeamAssignment(
                match_id=match_id,
                tracking_job_id=source.job.id,
                tracking_version=version,
                track_id=prediction.track_id,
            )
            session.add(assignment)
        assignment.classification_mode = mode
        assignment.classification_provenance = {
            "prototype_set_id": colors["id"] if colors else None,
            "sample_ids": [
                sample for p in colors["prototypes"] for sample in p["sample_ids"]
            ]
            if colors
            else [],
            "sample_count": prediction.sample_count,
            "accepted_sample_count": prediction.accepted_sample_count,
            "rejected_sample_count": prediction.rejected_sample_count,
            "margin": prediction.margin,
            "rejection_reason": prediction.rejection_reason,
        }
        assignment.automatic_team = prediction.team
        assignment.automatic_confidence = prediction.confidence
        assignment.updated_at = utc_now()
        # Do not overwrite manual_team or its author, including edits made while
        # sampling. Overrides and publication take the same short match-row lock.
    session.commit()
