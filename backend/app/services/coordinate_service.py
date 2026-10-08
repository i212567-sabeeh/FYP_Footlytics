"""Protected lightweight summaries for current coordinate artifacts."""

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
from app.schemas.coordinates import CoordinateResultRead, CoordinateSummary
from app.services.coordinate_artifacts import COLUMNS
from app.services.coordinate_inputs import current_mapping_inputs
from app.services.domain_common import DomainError
from app.services.match_service import get_match
from app.services.result_inputs import SUCCESS, result_artifact_path
from app.services.tracking_inputs import file_version


@dataclass(frozen=True)
class CoordinateSource:
    job: ProcessingJob
    summary: CoordinateSummary
    path: Path
    version: dict
    decoded_frames: int
    frame_stride: int
    duration: float


def get_summary(
    session: Session, user: User, match_id: int, settings: Settings
) -> CoordinateResultRead:
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for pitch coordinates.")
    match = get_match(session, user, match_id)
    result = current_coordinates(session, match, settings)
    return CoordinateResultRead(
        **result.summary.model_dump(),
        job_id=result.job.id,
        job_updated_at=result.job.updated_at,
        status=result.job.status,
        video_id=result.job.video_id,
    )


def current_coordinates(
    session: Session, match: Match, settings: Settings
) -> CoordinateSource:
    """Shared read-only guard; callers enforce resource access before use."""
    match_id = match.id
    inputs = current_mapping_inputs(session, match, settings)
    source, calibration = inputs.source, inputs.calibration
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match_id,
            ProcessingJob.video_id == source.video.id,
            ProcessingJob.job_type == JobType.COORDINATE_MAPPING,
            ProcessingJob.status.in_(SUCCESS),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        raise DomainError(409, "No pitch coordinate results are available yet.")
    if (
        job.tracking_snapshot != source.version
        or job.calibration_snapshot != calibration
    ):
        raise DomainError(
            409,
            "Pitch coordinates are stale. "
            "Map the current tracks with current calibration.",
        )
    try:
        data = CoordinateSummary.model_validate(job.coordinate_summary)
        assert source.tracking is not None
        if (
            data.tracking_job_id != source.job.id
            or data.tracking_attempt != source.job.attempt
            or data.calibration_id != calibration["id"]
            or data.calibration_updated_at.isoformat() != calibration["updated_at"]
            or data.pitch_length_metres != match.pitch_length_metres
            or data.pitch_width_metres != match.pitch_width_metres
            or data.total_rows != source.tracking.total_track_rows
            or data.unique_tracks > source.tracking.unique_tracks
            or (
                data.last_frame is not None
                and data.last_frame >= source.detection.decoded_frames
            )
            or any(
                number is not None and number % source.detection.frame_stride
                for number in (data.first_frame, data.last_frame)
            )
        ):
            raise ValueError("Mismatched coordinate provenance")
        path = result_artifact_path(job, settings, COLUMNS)
        if file_version(path) != job.coordinate_summary.get("artifact_version"):
            raise ValueError("Changed coordinate artifact")
    except (OSError, ValueError, TypeError, KeyError, csv.Error, DomainError):
        raise DomainError(
            409, "The pitch coordinate artifact or summary is invalid or unavailable."
        ) from None
    return CoordinateSource(
        job,
        data,
        path,
        {
            "upstream": source.version,
            "calibration": calibration,
            "job_id": job.id,
            "attempt": job.attempt,
            "job_updated_at": job.updated_at.isoformat(),
            "artifact": job.artifact_relative_path,
            "summary": job.coordinate_summary,
        },
        source.detection.decoded_frames,
        source.detection.frame_stride,
        source.video.duration_seconds,
    )
