"""Planar image → pitch geometry, independent of HTTP and database code.

Destination coordinates are metres (X length, Y width). A homography applies to
one planar surface and camera pose; its fitting residual is not ground-truth
accuracy or evidence that a moving camera remains calibrated.
"""

import cv2
import numpy as np
from numpy.typing import ArrayLike, NDArray

Matrix = NDArray[np.float64]


def _points(points: ArrayLike, minimum: int = 1) -> Matrix:
    try:
        array = np.asarray(points)
        if array.ndim != 2 or array.shape[1] != 2 or len(array) < minimum:
            raise ValueError
        if array.dtype.kind not in "iuf":
            raise ValueError
        array = np.asarray(array, dtype=np.float64)
        if not np.isfinite(array).all():
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError(
            f"Supply at least {minimum} finite numeric (x, y) points"
        ) from None
    return array


def validate_homography(matrix: ArrayLike) -> Matrix:
    """Return a normalized, finite, invertible 3×3 matrix; scale is arbitrary."""
    try:
        result = np.asarray(matrix)
        if result.shape != (3, 3) or result.dtype.kind not in "iuf":
            raise ValueError
        result = np.asarray(result, dtype=np.float64)
        scale = np.max(np.abs(result))
        if not np.isfinite(result).all() or scale == 0:
            raise ValueError
        result = result / scale
        singular = np.linalg.svd(result, compute_uv=False)
        if singular[-1] <= singular[0] * 1e-12:
            raise ValueError
        if abs(result[2, 2]) > 1e-12:
            result = result / result[2, 2]
    except (ValueError, TypeError, OverflowError, np.linalg.LinAlgError):
        raise ValueError(
            "Homography must be a finite, nonsingular 3×3 matrix"
        ) from None
    return result


def _denominators(points: Matrix, matrix: Matrix) -> Matrix:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    denominator = homogeneous @ matrix[2]
    tolerance = np.maximum(
        np.finfo(np.float32).eps,
        1e-10 * np.linalg.norm(matrix[2]) * np.linalg.norm(homogeneous, axis=1),
    )
    if np.any(np.abs(denominator) <= tolerance):
        raise ValueError("A point lies on or too close to the homography horizon")
    return denominator


def transform_points(points: ArrayLike, matrix: ArrayLike) -> list[tuple[float, float]]:
    """Transform a batch in one OpenCV call, without clamping pitch coordinates."""
    homography = validate_homography(matrix)
    if np.asarray(points).shape in {(0,), (0, 2)}:
        return []
    source = _points(points)
    _denominators(source, homography)
    try:
        result = cv2.perspectiveTransform(source.reshape(-1, 1, 2), homography)
    except cv2.error:
        raise ValueError(
            "The points cannot be transformed with this homography"
        ) from None
    result = result.reshape(-1, 2)
    if not np.isfinite(result).all():
        raise ValueError("The transformation produced non-finite coordinates")
    return [(float(x), float(y)) for x, y in result]


def transform_point(point: ArrayLike, matrix: ArrayLike) -> tuple[float, float]:
    return transform_points([point], matrix)[0]


def compute_reprojection_error(
    image_points: ArrayLike, pitch_points: ArrayLike, matrix: ArrayLike
) -> float:
    """Mean Euclidean error in metres over ALL supplied correspondences.

    This includes RANSAC outliers, so their disagreement stays visible. It is a fit
    residual, not an independent accuracy evaluation; four exact points can fit at zero.
    """
    image, pitch = _points(image_points), _points(pitch_points)
    if image.shape != pitch.shape:
        raise ValueError("Image and pitch point lists must have the same length")
    projected = np.asarray(transform_points(image, matrix))
    error = float(np.linalg.norm(projected - pitch, axis=1).mean())
    if not np.isfinite(error):
        raise ValueError("The reprojection error is not finite")
    return error


def _validate_geometry(image: Matrix, pitch: Matrix) -> None:
    """Normalized DLT needs rank 8 to constrain eight projective degrees of freedom.

    Normalization makes the rank check independent of pixel/metre scale. This catches
    duplicates, collinear sets and four-point sets with three collinear landmarks.
    """
    normalized = []
    for points in (image, pitch):
        if len(np.unique(points, axis=0)) != len(points):
            raise ValueError("Calibration landmarks must not contain duplicate points")
        centered = points - points.mean(axis=0)
        scale = np.linalg.norm(centered, axis=1).max()
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Calibration landmarks are degenerate")
        normalized.append(centered / scale)
    source, target = normalized
    x, y = source.T
    u, v = target.T
    zero, one = np.zeros(len(source)), np.ones(len(source))
    equations = np.vstack(
        (
            np.column_stack((-x, -y, -one, zero, zero, zero, u * x, u * y, u)),
            np.column_stack((zero, zero, zero, -x, -y, -one, v * x, v * y, v)),
        )
    )
    singular = np.linalg.svd(equations, compute_uv=False)
    if np.count_nonzero(singular > singular[0] * 1e-8) < 8:
        raise ValueError("Calibration landmarks are collinear or degenerate")


def compute_homography(
    image_points: ArrayLike,
    pitch_points: ArrayLike,
    *,
    ransac_threshold_metres: float = 0.5,
) -> Matrix:
    """Fit image pixels to metres; use RANSAC with more than four pairs.

    The 0.5 m default is an inlier-selection threshold in destination units, not a
    claimed measurement accuracy. Inputs stay ordered: image[i] corresponds to pitch[i].
    """
    image, pitch = _points(image_points, 4), _points(pitch_points, 4)
    if image.shape != pitch.shape:
        raise ValueError("Image and pitch point lists must have the same length")
    if not np.isfinite(ransac_threshold_metres) or ransac_threshold_metres <= 0:
        raise ValueError("The RANSAC threshold must be finite and positive")
    _validate_geometry(image, pitch)
    try:
        matrix, mask = cv2.findHomography(
            image,
            pitch,
            method=cv2.RANSAC if len(image) > 4 else 0,
            ransacReprojThreshold=ransac_threshold_metres,
            maxIters=2000,
            confidence=0.995,
        )
    except cv2.error:
        raise ValueError("These landmarks cannot produce a homography") from None
    matrix = validate_homography(matrix)
    if mask is None or mask.size != len(image):
        raise ValueError("Homography fitting did not identify valid correspondences")
    inliers = mask.reshape(-1).astype(bool)
    if np.count_nonzero(inliers) < 4:
        raise ValueError("At least four valid homography inliers are required")
    _validate_geometry(image[inliers], pitch[inliers])
    denominator = _denominators(image, matrix)
    if np.any(denominator < 0) and np.any(denominator > 0):
        raise ValueError(
            "Calibration crosses the projective horizon; check point ordering"
        )
    transform_points(image, matrix)
    return matrix
