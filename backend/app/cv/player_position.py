"""Approximate ground contact from tracked boxes, using Phase 5 homography.

The pitch is planar; calibration/camera error and occlusion propagate into these
positions. This module does no smoothing, identity repair or movement analytics.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from app.cv import homography

PITCH_TOLERANCE_METRES = 1e-6


@dataclass(frozen=True)
class PitchPosition:
    pixel_x: float
    pixel_y: float
    pitch_x: float
    pitch_y: float
    inside_pitch: bool


def bottom_center(box: Sequence[float]) -> tuple[float, float]:
    """The ground point is ((x1+x2)/2, y2), never the torso centre.

    Reject malformed boxes; preserve valid coordinates without clipping/repair.
    """
    try:
        values = np.asarray(box)
        if values.shape != (4,) or values.dtype.kind not in "iuf":
            raise ValueError
        x1, y1, x2, y2 = (float(value) for value in values)
        if (
            not all(math.isfinite(value) for value in (x1, y1, x2, y2))
            or x2 <= x1
            or y2 <= y1
        ):
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError(
            "A tracked box needs four finite, ordered coordinates"
        ) from None
    # Halving first avoids overflow for large, otherwise finite input values.
    return x1 / 2 + x2 / 2, y2


def inside_pitch(
    pitch_x: float, pitch_y: float, length_metres: float, width_metres: float
) -> bool:
    if (
        not all(
            math.isfinite(value)
            for value in (pitch_x, pitch_y, length_metres, width_metres)
        )
        or length_metres <= 0
        or width_metres <= 0
    ):
        raise ValueError("Pitch positions and positive dimensions must be finite")
    tolerance = PITCH_TOLERANCE_METRES
    return (
        -tolerance <= pitch_x <= length_metres + tolerance
        and -tolerance <= pitch_y <= width_metres + tolerance
    )


def map_ground_points(
    points: Sequence[tuple[float, float]],
    matrix: ArrayLike,
    length_metres: float,
    width_metres: float,
) -> list[PitchPosition]:
    """Use the existing perspectiveTransform/horizon checks on a bounded batch."""
    inside_pitch(
        0, 0, length_metres, width_metres
    )  # Validate dimensions even when empty.
    transformed = homography.transform_points(points, matrix)
    try:
        values = np.asarray(transformed, dtype=np.float64)
        if len(points) == 0 and values.shape == (0,):
            return []
        if values.shape != (len(points), 2) or not np.isfinite(values).all():
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Homography returned invalid pitch coordinates") from None
    return [
        PitchPosition(
            float(pixel[0]),
            float(pixel[1]),
            float(x),
            float(y),
            inside_pitch(float(x), float(y), length_metres, width_metres),
        )
        for pixel, (x, y) in zip(points, values, strict=True)
    ]
