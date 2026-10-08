"""Durable job lifecycle and shared match lock for media mutations."""

import logging
from uuid import uuid4

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.club_access import MATCH_ROLES, ensure_club_access, has_roles
from app.core.config import Settings
from app.core.jobs import (
    ACTIVE_JOB_STATUSES,
    RETRYABLE_JOB_STATUSES,
    JobStatus,
    JobType,
)
from app.database.base import utc_now
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.models.user import User
from app.schemas.media import ProcessingJobRead
from app.services.coordinate_inputs import current_mapping_inputs
from app.services.coordinate_service import current_coordinates
from app.services.detection_inputs import current_calibration, snapshot
from app.services.domain_common import DomainError, page_results
from app.services.match_service import get_match
from app.services.report_inputs import capture_inputs
from app.services.result_inputs import current_result
from app.services.tactics_inputs import current_tactics_inputs
from app.services.team_color_service import color_snapshot
from app.services.tracking_inputs import current_detection
from app.services.trajectory_service import current_trajectories
from app.workers.queue import JobQueue

logger = logging.getLogger(__name__)


def lock_match_for_media(session: Session, user: User, match_id: int) -> Match:
    """Serialize short replacement/create/retry transactions on the match row.

    PostgreSQL locks this row; SQLite takes its normal writer lock. End the auth
    read snapshot first so concurrent SQLite writers do not upgrade a stale read.
    Upload inspection and queue network calls must happen outside this lock.
    """
    get_match(session, user, match_id)
    session.rollback()
    session.execute(
        update(Match)
        .where(Match.id == match_id)
        .values(id=Match.id, updated_at=Match.updated_at)
        .execution_options(synchronize_session=False)
    )
    # Rollback expired the auth identity: these checks reload current account and
    # roles, including permission changes made while an upload was being checked.
    if not user.is_active:
        raise DomainError(401, "The account is inactive")
    if not has_roles(user, MATCH_ROLES):
        raise DomainError(403, "Match modification permission is required")
    match = get_match(session, user, match_id)
    ensure_club_access(session, user, match.club_id, write=True)
    if match.is_archived:
        raise DomainError(409, "Restore the match before changing its video or jobs")
    return match


def active_job(session: Session, match_id: int) -> ProcessingJob | None:
    return session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.match_id == match_id,
            ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )


def get_job(session: Session, user: User, job_id: int) -> ProcessingJob:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise DomainError(404, "Processing job not found")
    get_match(session, user, job.match_id)
    return job


def list_jobs(session: Session, user: User, match_id: int, offset: int, limit: int):
    get_match(session, user, match_id)
    statement = (
        select(ProcessingJob)
        .where(ProcessingJob.match_id == match_id)
        # A retried historical job must stay on the first page while active so
        # monitoring does not miss it behind newer terminal jobs.
        .order_by(
            case((ProcessingJob.status.in_(ACTIVE_JOB_STATUSES), 0), else_=1),
            ProcessingJob.created_at.desc(),
            ProcessingJob.id.desc(),
        )
    )
    return page_results(session, statement, ProcessingJobRead, offset, limit)


def _source_video(session: Session, match_id: int) -> MatchVideo:
    video = session.scalar(
        select(MatchVideo).where(
            MatchVideo.match_id == match_id, MatchVideo.is_active.is_(True)
        )
    )
    if video is None:
        raise DomainError(409, "Upload a valid match video before processing it")
    return video


def _commit_queued(session: Session, job: ProcessingJob) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DomainError(
            409, "A processing job is already active for this video"
        ) from None


def _enqueue(session: Session, job: ProcessingJob, queue: JobQueue) -> ProcessingJob:
    job_id, attempt, rq_id = job.id, job.attempt, job.rq_job_id
    assert rq_id is not None
    try:
        if job.job_type == JobType.PLAYER_DETECTION:
            queue.enqueue_player_detection(job_id, attempt, rq_id)
        elif job.job_type == JobType.PLAYER_TRACKING:
            queue.enqueue_player_tracking(job_id, attempt, rq_id)
        elif job.job_type == JobType.TEAM_CLASSIFICATION:
            queue.enqueue_team_classification(job_id, attempt, rq_id)
        elif job.job_type == JobType.COORDINATE_MAPPING:
            queue.enqueue_coordinate_mapping(job_id, attempt, rq_id)
        elif job.job_type == JobType.TRAJECTORY_CLEANING:
            queue.enqueue_trajectory_cleaning(job_id, attempt, rq_id)
        elif job.job_type == JobType.PLAYER_ANALYTICS:
            queue.enqueue_player_analytics(job_id, attempt, rq_id)
        elif job.job_type == JobType.TEAM_TACTICAL_ANALYTICS:
            queue.enqueue_team_tactical_analytics(job_id, attempt, rq_id)
        elif job.job_type == JobType.MATCH_REPORT:
            queue.enqueue_match_report(job_id, attempt, rq_id)
        else:
            queue.enqueue_video_preparation(job_id, attempt, rq_id)
    except Exception:
        logger.exception("Queue submission failed for processing job %s", job_id)
        # A lost Redis acknowledgement may follow actual delivery. Do not overwrite
        # a worker which already claimed the attempt; its status is authoritative.
        session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.attempt == attempt,
                ProcessingJob.status == JobStatus.QUEUED,
            )
            .values(
                status=JobStatus.FAILED,
                current_stage="queue_unavailable",
                finished_at=utc_now(),
                updated_at=utc_now(),
                error_message=(
                    "The processing queue is unavailable. Start Redis and retry."
                ),
            )
        )
        session.commit()
        raise DomainError(
            503,
            "Video processing could not be queued. Check job status and retry "
            "when the queue is available.",
        ) from None
    logger.info("Processing job %s enqueued", job_id)
    # A fast worker may already have changed the state. Never rewrite it as queued.
    session.expire_all()
    return session.get(ProcessingJob, job_id)


def _preparation_for_video(session: Session, video: MatchVideo) -> ProcessingJob | None:
    # Video contents are immutable through the API; replacing an upload creates
    # a new video ID. A successful preparation remains valid for this source.
    return session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == video.match_id,
            ProcessingJob.video_id == video.id,
            ProcessingJob.job_type == JobType.VIDEO_PREPARATION,
        )
        .order_by(
            case(
                (ProcessingJob.status.in_(ACTIVE_JOB_STATUSES), 0),
                (
                    ProcessingJob.status.in_(
                        (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)
                    ),
                    1,
                ),
                else_=2,
            ),
            ProcessingJob.id.desc(),
        )
    )


def current_preparation(
    session: Session, user: User, match_id: int
) -> ProcessingJob | None:
    get_match(session, user, match_id)
    video = session.scalar(
        select(MatchVideo).where(
            MatchVideo.match_id == match_id, MatchVideo.is_active.is_(True)
        )
    )
    return _preparation_for_video(session, video) if video is not None else None


def create_preparation(
    session: Session, user: User, match_id: int, queue: JobQueue
) -> ProcessingJob:
    return _create_job(session, user, match_id, queue, JobType.VIDEO_PREPARATION)


def create_detection(
    session: Session, user: User, match_id: int, queue: JobQueue
) -> ProcessingJob:
    return _create_job(session, user, match_id, queue, JobType.PLAYER_DETECTION)


def _create_job(
    session: Session,
    user: User,
    match_id: int,
    queue: JobQueue,
    job_type: JobType,
    settings: Settings | None = None,
) -> ProcessingJob:
    match = lock_match_for_media(session, user, match_id)
    video = _source_video(session, match_id)
    if job_type == JobType.VIDEO_PREPARATION:
        prepared = _preparation_for_video(session, video)
        if prepared is not None and prepared.status in (
            JobStatus.COMPLETED,
            JobStatus.COMPLETED_WITH_WARNINGS,
        ):
            session.commit()  # Release the match lock without enqueueing again.
            return prepared
    if active_job(session, match_id) is not None:
        raise DomainError(409, "A processing job is already queued or running")
    calibration = (
        snapshot(current_calibration(session, match, video))
        if job_type in (JobType.PLAYER_DETECTION, JobType.PLAYER_TRACKING)
        else None
    )
    detections = None
    tracking = None
    team_colors = None
    coordinates = None
    trajectories = None
    assignments = None
    report = None
    if job_type == JobType.PLAYER_TRACKING:
        assert settings is not None and calibration is not None
        _, detections = current_detection(session, match, video, calibration, settings)
    if job_type == JobType.TEAM_CLASSIFICATION:
        assert settings is not None
        tracking = current_result(session, match, "tracking", settings).version
        team_colors = color_snapshot(session, match_id, tracking)
    if job_type == JobType.COORDINATE_MAPPING:
        assert settings is not None
        inputs = current_mapping_inputs(session, match, settings)
        tracking, calibration = inputs.source.version, inputs.calibration
    if job_type == JobType.TRAJECTORY_CLEANING:
        assert settings is not None
        coordinates = current_coordinates(session, match, settings).version
    if job_type == JobType.PLAYER_ANALYTICS:
        assert settings is not None
        trajectories = current_trajectories(session, match, settings).version
    if job_type == JobType.TEAM_TACTICAL_ANALYTICS:
        assert settings is not None
        inputs = current_tactics_inputs(session, match, settings)
        trajectories, assignments = (
            inputs.trajectories.version,
            inputs.assignment_version,
        )
    if job_type == JobType.MATCH_REPORT:
        assert settings is not None
        report = capture_inputs(session, user, match_id, settings).snapshot
    job = ProcessingJob(
        match_id=match_id,
        video_id=video.id,
        job_type=job_type,
        calibration_snapshot=calibration,
        detection_snapshot=detections,
        tracking_snapshot=tracking,
        team_color_snapshot=team_colors,
        coordinate_snapshot=coordinates,
        trajectory_snapshot=trajectories,
        assignment_snapshot=assignments,
        report_snapshot=report,
        status=JobStatus.QUEUED,
        progress_percent=0,
        current_stage="queued",
        created_by_user_id=user.id,
        rq_job_id=uuid4().hex,
        retry_count=0,
        attempt=0,
    )
    session.add(job)
    _commit_queued(session, job)
    logger.info("Processing job %s created for match %s", job.id, match_id)
    return _enqueue(session, job, queue)


def create_tracking(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.PLAYER_TRACKING, settings
    )


def create_classification(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.TEAM_CLASSIFICATION, settings
    )


def create_coordinate_mapping(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.COORDINATE_MAPPING, settings
    )


def create_trajectory_cleaning(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.TRAJECTORY_CLEANING, settings
    )


def create_player_analytics(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.PLAYER_ANALYTICS, settings
    )


def create_team_tactical_analytics(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(
        session, user, match_id, queue, JobType.TEAM_TACTICAL_ANALYTICS, settings
    )


def create_match_report(
    session: Session, user: User, match_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    return _create_job(session, user, match_id, queue, JobType.MATCH_REPORT, settings)


def retry_job(
    session: Session, user: User, job_id: int, queue: JobQueue, settings: Settings
) -> ProcessingJob:
    match_id = get_job(session, user, job_id).match_id
    match = lock_match_for_media(session, user, match_id)
    job = session.get(ProcessingJob, job_id, populate_existing=True)
    assert job is not None
    if job.status not in RETRYABLE_JOB_STATUSES:
        raise DomainError(409, "Only failed or cancelled jobs can be retried")
    video = _source_video(session, match_id)
    if video.id != job.video_id:
        raise DomainError(
            409,
            "This job belongs to a replaced video. Process the current video instead.",
        )
    if active_job(session, match_id) is not None:
        raise DomainError(409, "A processing job is already queued or running")
    if job.job_type == JobType.VIDEO_PREPARATION:
        prepared = _preparation_for_video(session, video)
        if prepared is not None and prepared.status in (
            JobStatus.COMPLETED,
            JobStatus.COMPLETED_WITH_WARNINGS,
        ):
            raise DomainError(409, "The current video is already prepared.")
    if job.job_type in (JobType.PLAYER_DETECTION, JobType.PLAYER_TRACKING):
        job.calibration_snapshot = snapshot(current_calibration(session, match, video))
    if job.job_type == JobType.PLAYER_TRACKING:
        _, job.detection_snapshot = current_detection(
            session, match, video, job.calibration_snapshot, settings
        )
    if job.job_type == JobType.TEAM_CLASSIFICATION:
        job.tracking_snapshot = current_result(
            session, match, "tracking", settings
        ).version
        job.team_color_snapshot = color_snapshot(
            session, match_id, job.tracking_snapshot
        )
    if job.job_type == JobType.COORDINATE_MAPPING:
        inputs = current_mapping_inputs(session, match, settings)
        job.tracking_snapshot = inputs.source.version
        job.calibration_snapshot = inputs.calibration
    if job.job_type == JobType.TRAJECTORY_CLEANING:
        job.coordinate_snapshot = current_coordinates(session, match, settings).version
    if job.job_type == JobType.PLAYER_ANALYTICS:
        job.trajectory_snapshot = current_trajectories(session, match, settings).version
    if job.job_type == JobType.TEAM_TACTICAL_ANALYTICS:
        inputs = current_tactics_inputs(session, match, settings)
        job.trajectory_snapshot = inputs.trajectories.version
        job.assignment_snapshot = inputs.assignment_version
    if job.job_type == JobType.MATCH_REPORT:
        job.report_snapshot = capture_inputs(session, user, match_id, settings).snapshot
    job.detection_summary = None
    job.tracking_summary = None
    job.classification_summary = None
    job.coordinate_summary = None
    job.trajectory_summary = None
    job.analytics_summary = None
    job.tactics_summary = None
    job.report_summary = None
    job.artifact_relative_path = None
    job.status = JobStatus.QUEUED
    job.current_stage = "queued"
    job.progress_percent = 0
    job.started_at = job.finished_at = None
    job.error_message = job.warning_message = None
    job.retry_count += 1
    job.attempt += 1
    job.rq_job_id = uuid4().hex
    job.updated_at = utc_now()
    _commit_queued(session, job)
    logger.info("Retry %s requested for processing job %s", job.retry_count, job_id)
    return _enqueue(session, job, queue)
