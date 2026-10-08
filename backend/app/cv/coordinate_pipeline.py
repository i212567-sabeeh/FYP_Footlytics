"""Stream saved tracks through the existing homography, in bounded batches."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from numpy.typing import ArrayLike

from app.cv import homography
from app.cv.player_position import PitchPosition, bottom_center, map_ground_points
from app.cv.tracking_rows import TrackingRowsError, TrackObservation, tracking_rows
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary

MAPPING_BATCH_ROWS = 256


class CoordinateMappingError(Exception):
    """Safe messages only; never carry filenames or native exception text."""


@dataclass(frozen=True)
class CoordinateRun:
    total_rows: int
    valid_mapped_rows: int
    skipped_invalid_boxes: int
    inside_pitch_rows: int
    outside_pitch_rows: int
    unique_tracks: int
    first_frame: int | None
    last_frame: int | None


def map_tracking(
    path: Path,
    detection: DetectionSummary,
    tracking: TrackingSummary,
    duration: float,
    matrix: ArrayLike,
    length_metres: float,
    width_metres: float,
    *,
    write_position: Callable[[TrackObservation, PitchPosition], None],
    progress: Callable[[int, int], None],
) -> CoordinateRun:
    # Validate even for an empty artifact; never fit or infer a new calibration.
    try:
        matrix = homography.validate_homography(matrix)
        map_ground_points([], matrix, length_metres, width_metres)
    except ValueError as error:
        raise CoordinateMappingError(
            "The calibration cannot map pitch coordinates."
        ) from error
    total = skipped = mapped = inside = 0
    first = last = None
    seen: set[int] = set()
    mapped_tracks: set[int] = set()
    batch: list[tuple[TrackObservation, tuple[float, float]]] = []

    def flush() -> None:
        nonlocal mapped, inside, first, last
        if batch:
            try:
                positions = map_ground_points(
                    [point for _, point in batch], matrix, length_metres, width_metres
                )
            except (ValueError, TypeError, OverflowError) as error:
                raise CoordinateMappingError(
                    "A ground point could not be mapped safely. "
                    "Check the calibration and camera view."
                ) from error
            for (row, _), position in zip(batch, positions, strict=True):
                write_position(row, position)
                mapped += 1
                inside += int(position.inside_pitch)
                mapped_tracks.add(row.track_id)
                if first is None:
                    first = row.frame
                last = row.frame
            batch.clear()
        if total:
            progress(total, tracking.total_track_rows)

    rows = tracking_rows(path, detection, duration)
    try:
        for row in rows:
            total += 1
            seen.add(row.track_id)
            if total > tracking.total_track_rows or len(seen) > tracking.unique_tracks:
                raise CoordinateMappingError("The tracking row or track count changed.")
            try:
                point = bottom_center(row.box)
            except ValueError:
                skipped += 1  # No repair, no invented position; count the omission.
            else:
                batch.append((row, point))
            if total % MAPPING_BATCH_ROWS == 0:
                flush()
        if total != tracking.total_track_rows or len(seen) != tracking.unique_tracks:
            raise CoordinateMappingError(
                "The tracking artifact is incomplete or its summary changed."
            )
        if total % MAPPING_BATCH_ROWS:
            flush()
    except TrackingRowsError as error:
        raise CoordinateMappingError(str(error)) from error
    finally:
        rows.close()
    return CoordinateRun(
        total, mapped, skipped, inside, mapped - inside, len(mapped_tracks), first, last
    )
