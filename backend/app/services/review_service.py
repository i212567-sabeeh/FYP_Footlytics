"""Protected, current detection/tracking summaries and bounded single-frame review."""

import csv
import math
import time
from dataclasses import replace
from datetime import datetime

import cv2
from sqlalchemy.orm import Session

from app.auth.club_access import STAFF_ROLES, has_roles
from app.core.config import Settings
from app.cv.detector import is_reported
from app.cv.preview import PreviewBox, annotate_frame
from app.models.user import User
from app.schemas.review import DetectionReviewSummary, TrackingReviewSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.domain_common import DomainError
from app.services.frame_service import CalibrationFrame, extract_frame
from app.services.match_service import get_match
from app.services.result_inputs import ResultKind as ReviewKind
from app.services.result_inputs import ResultSource as ReviewSource
from app.services.result_inputs import current_result
from app.services.tracking_artifacts import COLUMNS as TRACKING_COLUMNS


def _source(
    session: Session, user: User, match_id: int, kind: ReviewKind, settings: Settings
) -> ReviewSource:
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for computer vision review.")
    return current_result(session, get_match(session, user, match_id), kind, settings)


def get_summary(
    session: Session, user: User, match_id: int, kind: ReviewKind, settings: Settings
) -> DetectionReviewSummary | TrackingReviewSummary:
    source = _source(session, user, match_id, kind, settings)
    data = source.detection
    common = dict(
        job_id=source.job.id,
        job_updated_at=source.job.updated_at,
        status=source.job.status,
        video_id=source.video.id,
        processed_frames=data.processed_frames,
        frame_stride=data.frame_stride,
        first_frame=0,
        last_frame=(data.processed_frames - 1) * data.frame_stride,
        frame_width=data.frame_width,
        frame_height=data.frame_height,
    )
    if source.tracking:
        return TrackingReviewSummary(
            **common,
            unique_tracks=source.tracking.unique_tracks,
            tracked_rows=source.tracking.total_track_rows,
            average_visible_tracks_per_frame=source.tracking.total_track_rows
            / data.processed_frames,
        )
    return DetectionReviewSummary(
        **common,
        total_detections=data.total_detections,
        average_detections_per_processed_frame=data.total_detections
        / data.processed_frames,
    )


def _observations(
    source: ReviewSource, requested: int | None, timeout: float
) -> tuple[int, list[PreviewBox]]:
    data = source.detection
    if requested is not None and (
        not 0 <= requested < data.decoded_frames or requested % data.frame_stride
    ):
        raise DomainError(
            422, "Choose a processed frame within the result range and sampling stride."
        )
    target = requested
    boxes: list[PreviewBox] = []
    previous, timestamp = -1, -1.0
    deadline = time.monotonic() + timeout
    rows_seen = 0
    try:
        with source.path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = TRACKING_COLUMNS if source.tracking else DETECTION_COLUMNS
            if tuple(reader.fieldnames or ()) != expected:
                raise ValueError("Changed header")
            for row in reader:
                rows_seen += 1
                if time.monotonic() > deadline:
                    raise DomainError(
                        422,
                        "Preview lookup timed out. Choose an earlier processed frame.",
                    )
                if len(row) != len(expected) or any(
                    value is None for value in row.values()
                ):
                    raise ValueError("Invalid row")
                number, seconds = (
                    int(row["frame_number"]),
                    float(row["timestamp_seconds"]),
                )
                if (
                    number < previous
                    or not 0 <= number < data.decoded_frames
                    or number % data.frame_stride
                    or not math.isfinite(seconds)
                    or seconds < 0
                    or (number == previous and seconds != timestamp)
                    or (number > previous and seconds < timestamp)
                ):
                    raise ValueError("Invalid frame metadata")
                previous, timestamp = number, seconds
                if target is None and (
                    source.tracking
                    or is_reported(float(row["confidence"]), data.confidence_threshold)
                ):
                    # Default to the first reported frame rather than a blank one.
                    target = number
                if target is None or number < target:
                    continue
                if number > target:
                    break
                box = tuple(float(row[name]) for name in ("x1", "y1", "x2", "y2"))
                confidence = float(row["confidence"])
                x1, y1, x2, y2 = box
                if (
                    not all(math.isfinite(value) for value in (*box, confidence))
                    or not 0 <= confidence <= 1
                    or not 0 <= x1 < x2 <= data.frame_width
                    or not 0 <= y1 < y2 <= data.frame_height
                ):
                    raise ValueError("Invalid box")
                track_id = int(row["track_id"]) if source.tracking else None
                if track_id is not None and track_id < 1:
                    raise ValueError("Invalid track ID")
                if not source.tracking and (
                    row["class_name"] != "person"
                    or int(row["class_id"]) < 0
                    or int(row["frame_width"]) != data.frame_width
                    or int(row["frame_height"]) != data.frame_height
                ):
                    raise ValueError("Invalid detection metadata")
                if not source.tracking and not is_reported(
                    confidence, data.confidence_threshold
                ):
                    if confidence < data.stored_confidence_threshold:
                        raise ValueError("Invalid detection confidence")
                    continue  # A ByteTrack-only candidate is never drawn as detected.
                boxes.append(PreviewBox(box, confidence, track_id))
                # Existing YOLO caps output at 300 per image. Bound corrupted CSV
                # memory use generously without changing valid detector output.
                if len(boxes) > 10000:
                    raise ValueError("Too many observations in one frame")
            else:
                total = (
                    source.tracking.total_track_rows
                    if source.tracking
                    else data.stored_detections
                )
                if rows_seen != total:
                    raise ValueError("Incomplete artifact")
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise DomainError(
            409, "The saved preview observations are invalid or unavailable."
        ) from None
    return target if target is not None else 0, boxes


def get_preview(
    session: Session,
    user: User,
    match_id: int,
    kind: ReviewKind,
    settings: Settings,
    frame_number: int | None,
    job_id: int | None,
    job_updated_at: datetime | None,
) -> tuple[CalibrationFrame, int, str]:
    source = _source(session, user, match_id, kind, settings)
    result_job_id, updated_at = source.job.id, source.job.updated_at
    if (job_id is not None and job_id != result_job_id) or (
        job_updated_at is not None and job_updated_at != updated_at
    ):
        raise DomainError(
            409,
            "The reviewed result changed. Refresh the review before loading a frame.",
        )
    session.commit()  # No read transaction spans CSV I/O or native video seeking.
    number, boxes = _observations(
        source, frame_number, settings.video_inspection_timeout_seconds
    )
    frame = extract_frame(source.video, 0, settings, frame_number=number)
    if (frame.width, frame.height) != (
        source.detection.frame_width,
        source.detection.frame_height,
    ):
        raise DomainError(
            409, "The frame dimensions do not match the saved observations."
        )
    try:
        frame = replace(frame, jpeg=annotate_frame(frame.jpeg, boxes))
    except (ValueError, cv2.error):
        raise DomainError(422, "The preview image could not be generated.") from None
    session.expire_all()
    current = _source(session, user, match_id, kind, settings)
    if source.version != current.version:
        raise DomainError(
            409, "The source or results changed during review. Refresh and try again."
        )
    return frame, result_job_id, updated_at.isoformat()
