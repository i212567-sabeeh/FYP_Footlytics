"""Shared current-result guards for saved previews and downstream processing."""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.jobs import JobStatus, JobType
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.detection_inputs import current_calibration, snapshot
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService
from app.services.tracking_artifacts import COLUMNS as TRACKING_COLUMNS
from app.services.tracking_inputs import current_detection, file_version

ResultKind = Literal["detections", "tracking"]
SUCCESS = (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)


@dataclass(frozen=True)
class ResultSource:
    video: MatchVideo
    job: ProcessingJob
    detection: DetectionSummary
    tracking: TrackingSummary | None
    path: Path
    version: dict


def result_artifact_path(
    job: ProcessingJob, settings: Settings, columns: tuple[str, ...]
) -> Path:
    relative = job.artifact_relative_path or ""
    prefix = (
        f"tracks/matches/{job.match_id}/videos/{job.video_id}/jobs/{job.id}/"
        f"attempt-{job.attempt}-"
    )
    if not relative.startswith(prefix) or not relative.endswith(".csv"):
        raise ValueError("Invalid artifact provenance")
    path = StorageService(settings).resolve(relative)
    file_version(path)  # Reject non-files before reading, including redirected paths.
    with path.open(encoding="utf-8", newline="") as stream:
        if tuple(next(csv.reader([stream.readline(4096)]), ())) != columns:
            raise ValueError("Invalid artifact header")
    return path


def current_result(
    session: Session, match: Match, kind: ResultKind, settings: Settings
) -> ResultSource:
    """Validate current provenance; callers enforce access before using this helper."""
    match_id = match.id
    # Keep this read-only guard independent of upload/job mutation services.
    video = session.scalar(
        select(MatchVideo).where(
            MatchVideo.match_id == match_id, MatchVideo.is_active.is_(True)
        )
    )
    if video is None:
        raise DomainError(409, "No active match video is available for review.")
    calibration = snapshot(current_calibration(session, match, video))
    detection, detection_version = current_detection(
        session, match, video, calibration, settings
    )
    job, tracking = detection, None
    if kind == "tracking":
        job = session.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.match_id == match_id,
                ProcessingJob.video_id == video.id,
                ProcessingJob.job_type == JobType.PLAYER_TRACKING,
                ProcessingJob.status.in_(SUCCESS),
            )
            .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
        )
        if job is None:
            raise DomainError(409, "No player tracking results are available yet.")
        if (
            job.calibration_snapshot != calibration
            or job.detection_snapshot != detection_version
        ):
            raise DomainError(
                409, "Tracking results are stale. Run tracking with current detections."
            )
    try:
        summary = DetectionSummary.model_validate(detection.detection_summary)
        if kind == "tracking":
            tracking = TrackingSummary.model_validate(job.tracking_summary)
            if (
                tracking.detection_job_id != detection.id
                or tracking.detection_attempt != detection.attempt
                or tracking.processed_frames != summary.processed_frames
                or tracking.total_detections != summary.total_detections
                or tracking.low_confidence_detections
                != summary.low_confidence_detections
                or tracking.frame_stride != summary.frame_stride
                or (tracking.frame_width, tracking.frame_height)
                != (summary.frame_width, summary.frame_height)
                or not 0
                <= tracking.unique_tracks
                <= tracking.total_track_rows
                <= summary.stored_detections  # Candidates may extend tracks.
                or tracking.artifact_format != "csv"
            ):
                raise ValueError("Invalid tracking summary")
        path = result_artifact_path(
            job, settings, TRACKING_COLUMNS if tracking else DETECTION_COLUMNS
        )
        video_path = StorageService(settings).resolve(video.relative_storage_path)
        video_version = file_version(video_path)
        if video_version["size"] != video.file_size_bytes:
            raise ValueError("Changed source video")
        version = {
            "video_id": video.id,
            "video_updated_at": video.updated_at.isoformat(),
            "video_file": video_version,
            "calibration": calibration,
            "detections": detection_version,
            "job_id": job.id,
            "attempt": job.attempt,
            "job_updated_at": job.updated_at.isoformat(),
            "artifact": job.artifact_relative_path,
            "artifact_version": file_version(path),
            "tracking_summary": job.tracking_summary,
        }
    except (OSError, ValueError, TypeError, csv.Error, DomainError):
        raise DomainError(
            409, "The current result artifact or source video is missing or invalid."
        ) from None
    return ResultSource(video, job, summary, tracking, path, version)
