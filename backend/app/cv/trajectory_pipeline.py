"""External sorting followed by bounded per-track cleaning and streamed output."""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import Settings
from app.cv.coordinate_rows import TrajectoryError, ordered_coordinates
from app.cv.trajectory import TrajectoryObservation, clean_track
from app.schemas.coordinates import CoordinateSummary

PROGRESS_ROWS = 256


@dataclass(frozen=True)
class TrajectoryRun:
    source_rows: int = 0
    usable_rows: int = 0
    rejected_rows: int = 0
    outside_pitch_rows: int = 0
    jump_outlier_rows: int = 0
    invalid_temporal_rows: int = 0
    interpolated_rows: int = 0
    smoothed_rows: int = 0
    unique_tracks: int = 0
    segments: int = 0
    first_frame: int | None = None
    last_frame: int | None = None


def clean_coordinates(
    path: Path,
    summary: CoordinateSummary,
    decoded_frames: int,
    frame_stride: int,
    duration: float,
    settings: Settings,
    scratch_parent: Path,
    *,
    write_observation: Callable[[TrajectoryObservation], None],
    progress: Callable[[str, int, int], None],
) -> TrajectoryRun:
    total = summary.valid_mapped_rows
    rows_done = usable = outside = outliers = invalid_time = smoothed = tracks = (
        segments
    ) = 0
    first = last = None
    with TemporaryDirectory(prefix="trajectory-", dir=scratch_parent) as workspace:
        ordered = ordered_coordinates(
            path,
            summary,
            decoded_frames,
            frame_stride,
            duration,
            Path(workspace),
            lambda done, count: progress("loading_coordinates", done, count),
        )
        try:
            for _, observations in groupby(ordered, key=lambda row: row.track_id):
                tracks += 1
                if tracks > summary.unique_tracks:
                    raise TrajectoryError("The coordinate track count changed.")
                for point in clean_track(
                    observations,
                    settings,
                    summary.pitch_length_metres,
                    summary.pitch_width_metres,
                ):
                    write_observation(point)
                    rows_done += 1
                    usable += point.usable
                    outside += point.status == "outside_pitch"
                    outliers += point.status == "jump_outlier"
                    invalid_time += point.status == "invalid_temporal"
                    smoothed += point.status == "smoothed"
                    segments += point.status == "segment_start"
                    frame = point.raw.frame
                    first = frame if first is None else min(first, frame)
                    last = frame if last is None else max(last, frame)
                    if rows_done % PROGRESS_ROWS == 0:
                        progress("cleaning_tracks", rows_done, total)
            if rows_done != total or tracks != summary.unique_tracks:
                raise TrajectoryError("The coordinate row or track count changed.")
            progress("cleaning_tracks", rows_done, total)
        finally:
            ordered.close()
    return TrajectoryRun(
        rows_done,
        usable,
        rows_done - usable,
        outside,
        outliers,
        invalid_time,
        0,
        smoothed,
        tracks,
        segments,
        first,
        last,
    )
