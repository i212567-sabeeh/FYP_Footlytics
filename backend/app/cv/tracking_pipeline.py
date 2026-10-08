"""Stream ordered detection rows, including empty sampled frames, into a tracker."""

import csv
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from app.cv.detector import Detection, is_reported
from app.cv.tracker import BaseTracker, TrackedDetection, TrackingError
from app.cv.tracking_rows import within_video
from app.schemas.detection import DetectionSummary
from app.services.detection_artifacts import COLUMNS

OUTSIDE_VIDEO = (
    "Some detection timestamps are not within the stored video duration. Re-encode "
    "and replace the source video, then run detection and tracking again."
)


def detection_frames(
    path: Path, summary: DetectionSummary, duration: float
) -> Iterator[tuple[int, float, list[Detection]]]:
    """Hold at most one frame's detections; reject corrupt/unordered source rows.

    Detection CSVs omit empty frames. The persisted decoded count and stride define
    the exact sampling schedule. Empty updates carry no invented output timestamp.
    Every timestamp must pass within_video(), the rule all tracking-CSV readers
    apply to the stored duration. Rows below the reported threshold are stored
    ByteTrack low-score candidates and are counted separately.
    """
    observed = low = 0
    previous_frame, previous_timestamp = -1, -1.0
    stored_threshold = summary.stored_confidence_threshold
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError("Invalid CSV header")

            def read_row():
                nonlocal observed, low, previous_frame, previous_timestamp
                row = next(reader, None)
                if row is None:
                    return None
                if len(row) != len(COLUMNS) or any(
                    value is None for value in row.values()
                ):
                    raise ValueError("Invalid CSV row")
                number, timestamp = (
                    int(row["frame_number"]),
                    float(row["timestamp_seconds"]),
                )
                if (
                    not 0 <= number < summary.decoded_frames
                    or number % summary.frame_stride
                    or number < previous_frame
                    or not math.isfinite(timestamp)
                    or timestamp < 0
                    or (number == previous_frame and timestamp != previous_timestamp)
                    or (number > previous_frame and timestamp < previous_timestamp)
                    or int(row["frame_width"]) != summary.frame_width
                    or int(row["frame_height"]) != summary.frame_height
                    or int(row["class_id"]) < 0
                    or row["class_name"] != "person"
                ):
                    raise ValueError("Invalid frame metadata")
                box = tuple(float(row[name]) for name in ("x1", "y1", "x2", "y2"))
                confidence = float(row["confidence"])
                x1, y1, x2, y2 = box
                if (
                    not all(math.isfinite(value) for value in (*box, confidence))
                    or not stored_threshold <= confidence <= 1
                    or not (0 <= x1 < x2 <= summary.frame_width)
                    or not (0 <= y1 < y2 <= summary.frame_height)
                ):
                    raise ValueError("Invalid person box")
                if not within_video(timestamp, duration):
                    raise TrackingError(OUTSIDE_VIDEO)
                observed += 1
                low += not is_reported(confidence, summary.confidence_threshold)
                if observed > summary.stored_detections:
                    raise ValueError("Detection count mismatch")
                previous_frame, previous_timestamp = number, timestamp
                return (
                    number,
                    timestamp,
                    Detection(box, confidence, int(row["class_id"]), "person"),
                )

            upcoming = read_row()
            for number in range(0, summary.decoded_frames, summary.frame_stride):
                detections = []
                timestamp = 0.0  # Never written for an empty frame.
                while upcoming is not None and upcoming[0] == number:
                    timestamp = upcoming[1]
                    detections.append(upcoming[2])
                    upcoming = read_row()
                yield number, timestamp, detections
            if (
                upcoming is not None
                or observed != summary.stored_detections
                or low != summary.low_confidence_detections
            ):
                raise ValueError("Detection count mismatch")
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as error:
        raise TrackingError(
            "The detection CSV is invalid or incomplete. Run player detection again."
        ) from error


@dataclass(frozen=True)
class TrackingRun:
    processed_frames: int
    total_detections: int  # Reported detections, as in the detection summary.
    total_track_rows: int
    unique_tracks: int
    low_confidence_detections: int = 0  # Stored ByteTrack-only candidates.


def track_detections(
    path: Path,
    summary: DetectionSummary,
    tracker: BaseTracker,
    *,
    duration: float,
    write_frame: Callable[[int, float, list[TrackedDetection]], None],
    progress: Callable[[int, int], None],
) -> TrackingRun:
    processed = reported = low = rows = 0
    identifiers: set[int] = set()
    for number, timestamp, detections in detection_frames(path, summary, duration):
        tracks = tracker.update(detections)
        # ByteTrack only emits confirmed associations with current observations.
        # Never write predictions for a missed detection or invent gap timestamps.
        if tracks and not detections:
            raise TrackingError("The tracker returned observations for an empty frame.")
        write_frame(number, timestamp, tracks)
        processed += 1
        frame_reported = sum(
            is_reported(item.confidence, summary.confidence_threshold)
            for item in detections
        )
        reported += frame_reported
        low += len(detections) - frame_reported
        rows += len(tracks)
        identifiers.update(track.track_id for track in tracks)
        progress(processed, summary.processed_frames)
    return TrackingRun(processed, reported, rows, len(identifiers), low)
