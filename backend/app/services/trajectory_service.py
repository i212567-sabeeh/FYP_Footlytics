"""Protected current trajectory summaries; never return complete CSVs as JSON."""

import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import STAFF_ROLES, has_roles
from app.core.config import Settings
from app.core.jobs import JobType
from app.models.football import Match
from app.models.media import ProcessingJob
from app.models.user import User
from app.schemas.trajectories import TrajectoryResultRead, TrajectorySummary
from app.services.coordinate_service import current_coordinates
from app.services.domain_common import DomainError
from app.services.match_service import get_match
from app.services.result_inputs import SUCCESS, result_artifact_path
from app.services.tracking_inputs import file_version
from app.services.trajectory_artifacts import COLUMNS


@dataclass(frozen=True)
class TrajectorySource:
    job: ProcessingJob
    summary: TrajectorySummary
    path: Path
    version: dict
    decoded_frames: int
    frame_stride: int
    duration: float


def get_summary(
    session: Session,
    user: User,
    match_id: int,
    settings: Settings,
) -> TrajectoryResultRead:
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for trajectories.")
    match = get_match(session, user, match_id)
    result = current_trajectories(session, match, settings)
    return TrajectoryResultRead(
        **result.summary.model_dump(),
        job_id=result.job.id,
        job_updated_at=result.job.updated_at,
        status=result.job.status,
        video_id=result.job.video_id,
    )


def current_trajectories(
    session: Session, match: Match, settings: Settings
) -> TrajectorySource:
    """Shared provenance guard; callers authorize access before reading artifacts."""
    source = current_coordinates(session, match, settings)
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match.id,
            ProcessingJob.video_id == source.job.video_id,
            ProcessingJob.job_type == JobType.TRAJECTORY_CLEANING,
            ProcessingJob.status.in_(SUCCESS),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        raise DomainError(409, "No cleaned trajectory results are available yet.")
    if job.coordinate_snapshot != source.version:
        raise DomainError(409, "Trajectories are stale. Clean the current coordinates.")
    try:
        data = TrajectorySummary.model_validate(job.trajectory_summary)
        if (
            data.coordinate_job_id != source.job.id
            or data.coordinate_attempt != source.job.attempt
            or data.source_rows != source.summary.valid_mapped_rows
            or data.unique_tracks != source.summary.unique_tracks
            or data.outside_pitch_rows != source.summary.outside_pitch_rows
            or (data.first_frame, data.last_frame)
            != (source.summary.first_frame, source.summary.last_frame)
            or data.pitch_length_metres != match.pitch_length_metres
            or data.pitch_width_metres != match.pitch_width_metres
        ):
            raise ValueError("Mismatched trajectory provenance")
        path = result_artifact_path(job, settings, COLUMNS)
        if file_version(path) != job.trajectory_summary.get("artifact_version"):
            raise ValueError("Trajectory artifact changed")
    except (OSError, ValueError, TypeError, KeyError, csv.Error, DomainError):
        raise DomainError(
            409, "The trajectory artifact or summary is invalid or unavailable."
        ) from None
    return TrajectorySource(
        job,
        data,
        path,
        {
            "upstream": source.version,
            "job_id": job.id,
            "attempt": job.attempt,
            "job_updated_at": job.updated_at.isoformat(),
            "artifact": job.artifact_relative_path,
            "summary": job.trajectory_summary,
        },
        source.decoded_frames,
        source.frame_stride,
        source.duration,
    )
