"""Bind tracking to a completed, current detection attempt and protected CSV."""

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.jobs import JobStatus, JobType
from app.models.football import Match
from app.models.media import MatchVideo, ProcessingJob
from app.schemas.detection import DetectionSummary
from app.services.detection_artifacts import COLUMNS
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService


def file_version(path: Path) -> dict[str, int]:
    # Size and modification time are portable when Windows queues for a WSL
    # worker on the same storage. Device/inode and ctime have different meanings.
    stat = path.stat()
    if not path.is_file():
        raise OSError("Artifact is not a regular file")
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def current_detection(
    session: Session,
    match: Match,
    video: MatchVideo,
    calibration: dict,
    settings: Settings,
) -> tuple[ProcessingJob, dict]:
    job = session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.match_id == match.id,
            ProcessingJob.video_id == video.id,
            ProcessingJob.job_type == JobType.PLAYER_DETECTION,
            ProcessingJob.status.in_(
                (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc())
    )
    if job is None:
        raise DomainError(
            409, "Current detections are missing. Run player detection before tracking."
        )
    if job.calibration_snapshot != calibration:
        raise DomainError(
            409,
            "Detections are stale for this calibration. Run player detection again.",
        )
    try:
        summary = DetectionSummary.model_validate(job.detection_summary)
        stride, decoded = summary.frame_stride, summary.decoded_frames
        if (
            stride < 1
            or decoded < 1
            or summary.processed_frames != (decoded + stride - 1) // stride
            or summary.total_detections < 0
            or summary.low_confidence_detections < 0
            or not 0
            < summary.stored_confidence_threshold
            <= summary.confidence_threshold
            or (
                summary.candidate_confidence_threshold is None
                and summary.low_confidence_detections
            )
            or (summary.frame_width, summary.frame_height)
            != (video.width, video.height)
            or (summary.frame_width, summary.frame_height)
            != (calibration["image_width"], calibration["image_height"])
            or summary.calibration_id != calibration["id"]
            or summary.calibration_updated_at.isoformat() != calibration["updated_at"]
            or summary.artifact_format != "csv"
        ):
            raise ValueError("Invalid detection summary")
        relative = job.artifact_relative_path or ""
        prefix = (
            f"tracks/matches/{match.id}/videos/{video.id}/jobs/{job.id}/"
            f"attempt-{job.attempt}-"
        )
        if not relative.startswith(prefix) or not relative.endswith(".csv"):
            raise ValueError("Artifact does not belong to this detection attempt")
        path = StorageService(settings).resolve(relative)
        version = file_version(path)
        # Bounded validation while holding the short match lock. Full CSV validation
        # happens incrementally in the worker, never inside the HTTP request.
        with path.open(encoding="utf-8", newline="") as stream:
            if tuple(next(csv.reader([stream.readline(4096)]), ())) != COLUMNS:
                raise ValueError("Invalid detection CSV header")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        csv.Error,
        DomainError,
    ):
        raise DomainError(
            409,
            "The current detection artifact is missing or invalid. "
            "Run player detection again before tracking.",
        ) from None
    return job, {
        "job_id": job.id,
        "attempt": job.attempt,
        "updated_at": job.updated_at.isoformat(),
        "artifact_relative_path": relative,
        "summary": job.detection_summary,
        "file_version": version,
    }
