"""Read only Phase 10 clean positions, checking its ordered CSV and row metadata."""

import csv
import math
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.cv.player_position import inside_pitch
from app.schemas.trajectories import TrajectorySummary
from app.services.trajectory_artifacts import COLUMNS


class AnalyticsError(Exception):
    """Safe error suitable for durable processing job failures."""


@dataclass(frozen=True)
class CleanObservation:
    frame: int
    timestamp: float
    track_id: int
    segment_id: int | None
    clean: tuple[float, float] | None


def read_trajectories(
    path: Path,
    summary: TrajectorySummary,
    decoded_frames: int,
    frame_stride: int,
    duration: float,
) -> Iterator[CleanObservation]:
    counts: Counter[str] = Counter()
    previous_key = None
    last_track = last_segment = 0
    tracks = segments = count = 0
    first_frame = last_frame = None
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError("Unexpected trajectory columns")
            for count, row in enumerate(reader, 1):
                if (
                    None in row
                    or any(value is None for value in row.values())
                    or count > summary.source_rows
                ):
                    raise ValueError("Invalid trajectory row")
                frame, track = int(row["frame_number"]), int(row["track_id"])
                timestamp, source_row = (
                    float(row["timestamp_seconds"]),
                    int(row["source_row_number"]),
                )
                key = track, timestamp, frame, source_row
                if (
                    not math.isfinite(timestamp)
                    or timestamp >= duration
                    or not 0 < track < 2**63
                    or not 0 <= frame < decoded_frames
                    or frame % frame_stride
                    or not 1 <= source_row <= summary.source_rows
                    or (previous_key is not None and key <= previous_key)
                ):
                    raise ValueError("Invalid or unordered trajectory observations")
                previous_key = key
                if track != last_track:
                    tracks += 1
                    last_track, last_segment = track, 0
                first_frame = frame if first_frame is None else min(first_frame, frame)
                last_frame = frame if last_frame is None else max(last_frame, frame)
                if (
                    row["usable"] not in ("true", "false")
                    or row["is_interpolated"] != "false"
                ):
                    raise ValueError("Invalid usability metadata")
                status = row["status"]
                counts[status] += 1
                if row["usable"] == "false":
                    if (
                        status
                        not in ("outside_pitch", "jump_outlier", "invalid_temporal")
                        or row["clean_pitch_x"]
                        or row["clean_pitch_y"]
                        or row["segment_id"]
                    ):
                        raise ValueError("Rejected row has inconsistent clean data")
                    yield CleanObservation(frame, timestamp, track, None, None)
                    continue
                clean = float(row["clean_pitch_x"]), float(row["clean_pitch_y"])
                segment = int(row["segment_id"])
                if (
                    status not in ("accepted", "smoothed", "segment_start")
                    or timestamp < 0
                    or row["inside_pitch"] != "true"
                    or not 0 < segment < 2**63
                    or segment < last_segment
                    or not all(math.isfinite(value) for value in clean)
                    or not inside_pitch(
                        *clean, summary.pitch_length_metres, summary.pitch_width_metres
                    )
                ):
                    raise ValueError("Invalid usable cleaned position")
                if segment != last_segment:
                    segments += 1
                    last_segment = segment
                yield CleanObservation(frame, timestamp, track, segment, clean)
        if (
            count != summary.source_rows
            or tracks != summary.unique_tracks
            or segments != summary.segments
            or counts["accepted"] + counts["smoothed"] + counts["segment_start"]
            != summary.usable_rows
            or counts["smoothed"] != summary.smoothed_rows
            or counts["outside_pitch"] != summary.outside_pitch_rows
            or counts["jump_outlier"] != summary.jump_outlier_rows
            or counts["invalid_temporal"] != summary.invalid_temporal_rows
            or (first_frame, last_frame) != (summary.first_frame, summary.last_frame)
        ):
            raise ValueError("Trajectory counts do not match provenance")
    except (OSError, ValueError, TypeError, KeyError, csv.Error):
        raise AnalyticsError(
            "The cleaned trajectory artifact is invalid or unavailable."
        ) from None
