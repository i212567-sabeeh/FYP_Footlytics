"""Conservative image-space pitch ROI; no detection-to-metres transformation."""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.cv.detector import Detection


@dataclass(frozen=True)
class PitchROI:
    polygon: NDArray[np.float32]

    def contains(self, detection: Detection) -> bool:
        # A two-pixel boundary tolerance avoids rejecting rounding at touchlines.
        return cv2.pointPolygonTest(self.polygon, detection.bottom_centre, True) >= -2.0


def build_pitch_roi(
    image_points: list[dict[str, float]],
    pitch_points: list[dict[str, float]],
    length: float,
    width: float,
    image_width: int,
    image_height: int,
) -> PitchROI | None:
    """Use only explicitly paired four pitch corners, in boundary order.

    The convex hull of arbitrary landmarks is usually only part of a football
    pitch. It must never be treated as the complete playable region.
    """
    if len(image_points) != len(pitch_points):
        return None
    polygon = []
    for corner in ((0, 0), (length, 0), (length, width), (0, width)):
        matches = [
            image
            for image, pitch in zip(image_points, pitch_points, strict=True)
            if abs(pitch["x"] - corner[0]) <= 1e-4
            and abs(pitch["y"] - corner[1]) <= 1e-4
        ]
        if len(matches) != 1:
            return None
        polygon.append((matches[0]["x"], matches[0]["y"]))
    contour = np.asarray(polygon, dtype=np.float32)
    if (
        not np.isfinite(contour).all()
        or np.any(contour < 0)
        or np.any(contour[:, 0] > image_width - 1)
        or np.any(contour[:, 1] > image_height - 1)
        or not cv2.isContourConvex(contour)
        or cv2.contourArea(contour) < 4
    ):
        return None
    return PitchROI(contour)
