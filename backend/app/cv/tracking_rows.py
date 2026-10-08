"""Streaming saved track rows shared by jersey sampling and pitch mapping."""

import csv
import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.schemas.detection import DetectionSummary
from app.services.tracking_artifacts import COLUMNS

MAX_FRAME_TRACKS = 10000


class TrackingRowsError(Exception):
    """Curated failure for malformed metadata, ordering or unavailable CSVs."""


def within_video(seconds: float, duration: float) -> bool:
    """A frame starts in [0, duration) of the stored, positive video duration.

    Tracking applies this rule before publishing and every reader applies it
    again, so a completed tracking job never writes rows its consumers reject.
    """
    return (
        math.isfinite(duration)
        and duration > 0
        and math.isfinite(seconds)
        and 0 <= seconds < duration
    )


@dataclass(frozen=True)
class TrackObservation:
    frame: int
    timestamp: float
    track_id: int
    box: tuple[float, ...]
    confidence: float


def tracking_rows(
    path: Path, summary: DetectionSummary, duration: float
) -> Iterator[TrackObservation]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError("Header changed")
            previous, timestamp = -1, -1.0
            ids: set[int] = set()
            for row in reader:
                if len(row) != len(COLUMNS) or any(
                    value is None for value in row.values()
                ):
                    raise ValueError("Invalid row")
                number, seconds, track_id = (
                    int(row["frame_number"]),
                    float(row["timestamp_seconds"]),
                    int(row["track_id"]),
                )
                confidence = float(row["confidence"])
                if (
                    number < previous
                    or not 0 <= number < summary.decoded_frames
                    or number % summary.frame_stride
                    or not within_video(seconds, duration)
                    or (number == previous and seconds != timestamp)
                    or (number > previous and seconds < timestamp)
                    or not 0 < track_id <= 2**63 - 1
                    or not math.isfinite(confidence)
                    or not 0 <= confidence <= 1
                ):
                    raise ValueError("Invalid tracking metadata")
                if number != previous:
                    ids.clear()
                if track_id in ids or len(ids) >= MAX_FRAME_TRACKS:
                    raise ValueError("Duplicate or excessive observations")
                ids.add(track_id)
                previous, timestamp = number, seconds
                try:
                    box = tuple(float(row[key]) for key in ("x1", "y1", "x2", "y2"))
                except ValueError:
                    box = ()  # Malformed crops contribute no color evidence.
                yield TrackObservation(number, seconds, track_id, box, confidence)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, csv.Error):
        raise TrackingRowsError(
            "The tracking CSV is invalid or unavailable. Run tracking again."
        ) from None
