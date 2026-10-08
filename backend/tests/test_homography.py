"""Analytically known geometry; no video, database, models or network."""

import cv2
import numpy as np
import pytest

from app.cv import homography as geometry

RECTANGLE = [(0, 0), (100, 0), (100, 50), (0, 50)]


@pytest.mark.parametrize("length,width", [(100, 50), (105, 68), (40, 20)])
def test_identity_and_scaled_pitch_mappings(length, width):
    target = [(0, 0), (length, 0), (length, width), (0, width)]
    matrix = geometry.compute_homography(RECTANGLE, target)
    np.testing.assert_allclose(
        geometry.transform_points(RECTANGLE, matrix), target, atol=1e-6
    )
    np.testing.assert_allclose(
        geometry.transform_point((50, 25), matrix), (length / 2, width / 2), atol=1e-6
    )
    assert geometry.compute_reprojection_error(RECTANGLE, target, matrix) < 1e-6


def test_batch_uses_one_opencv_call_and_empty_batch_is_empty(monkeypatch):
    calls = []
    real_transform = cv2.perspectiveTransform

    def transform(*args):
        calls.append(args[0].shape)
        return real_transform(*args)

    monkeypatch.setattr(cv2, "perspectiveTransform", transform)
    assert geometry.transform_points([], np.eye(3)) == []
    points = [(index, index / 2) for index in range(100)]
    np.testing.assert_allclose(geometry.transform_points(points, np.eye(3)), points)
    assert calls == [(100, 1, 2)]


def test_perspective_mapping_and_arbitrary_matrix_scale():
    known = np.array([[0.1, 0.02, 3], [0.01, 0.2, 4], [0.001, 0.002, 1]])
    target = geometry.transform_points(RECTANGLE, known)
    fitted = geometry.compute_homography(RECTANGLE, target)
    point = (43, 27)
    np.testing.assert_allclose(
        geometry.transform_point(point, fitted),
        geometry.transform_point(point, known),
        atol=1e-5,
    )
    np.testing.assert_allclose(
        geometry.transform_point(point, known * 1e-20),
        geometry.transform_point(point, known),
        atol=1e-10,
    )


def test_more_than_four_points_uses_ransac_and_error_includes_outlier(monkeypatch):
    image = RECTANGLE + [(25, 15), (70, 25), (50, 40), (50, 10)]
    pitch = image[:-1] + [(80, 40)]
    original_fit = cv2.findHomography
    methods = []

    def fit(*args, **kwargs):
        methods.append(kwargs["method"])
        return original_fit(*args, **kwargs)

    monkeypatch.setattr(cv2, "findHomography", fit)
    matrix = geometry.compute_homography(image, pitch)
    np.testing.assert_allclose(
        geometry.transform_point((50, 25), matrix), (50, 25), atol=1e-6
    )
    assert methods == [cv2.RANSAC]
    assert geometry.compute_reprojection_error(image, pitch, matrix) == pytest.approx(
        np.hypot(30, 30) / 8
    )


@pytest.mark.parametrize(
    "image,pitch",
    [
        (RECTANGLE[:3], RECTANGLE[:3]),
        (RECTANGLE, RECTANGLE + [(50, 25)]),
        ([RECTANGLE[0]] * 4, RECTANGLE),
        (RECTANGLE, [RECTANGLE[0]] * 4),
        ([(0, 0), (1, 1), (2, 2), (3, 3)], RECTANGLE),
        (RECTANGLE, [(0, 0), (1, 1), (2, 2), (3, 3)]),
        ([(0, 0), (1, 0), (2, 0), (1, 1)], [(0, 0), (2, 0), (4, 0), (2, 2)]),
        ([(0, 0), (100, 0), (100, 1e-10), (0, 1e-10)], RECTANGLE),
        (RECTANGLE, [RECTANGLE[i] for i in (0, 2, 1, 3)]),
    ],
)
def test_invalid_correspondences_rejected(image, pitch):
    with pytest.raises(ValueError):
        geometry.compute_homography(image, pitch)


@pytest.mark.parametrize(
    "matrix",
    [
        None,
        np.zeros((3, 3)),
        np.eye(2),
        np.full((3, 3), np.nan),
        np.full((3, 3), np.inf),
        [[1, 0, 0], [1, 0, 0], [0, 0, 1]],
    ],
)
def test_invalid_matrix_rejected(matrix):
    with pytest.raises(ValueError):
        geometry.transform_point((1, 2), matrix)


@pytest.mark.parametrize(
    "points",
    [[(1, 2, 3)], [(np.nan, 1)], [(1, np.inf)], [(True, False)], [("1", "2")], [None]],
)
def test_invalid_point_input_rejected(points):
    with pytest.raises(ValueError):
        geometry.transform_points(points, np.eye(3))


def test_point_at_horizon_rejected_and_valid_points_are_not_clamped():
    matrix = [[1, 0, 0], [0, 1, 0], [1, 0, -1]]
    with pytest.raises(ValueError, match="horizon"):
        geometry.transform_point((1, 5), matrix)
    assert geometry.transform_point((-2, 80), np.eye(3)) == pytest.approx((-2, 80))


@pytest.mark.parametrize(
    "matrix", [None, np.zeros((3, 3)), np.full((3, 3), np.nan), np.full((3, 3), np.inf)]
)
def test_invalid_opencv_result_rejected(monkeypatch, matrix):
    monkeypatch.setattr(
        cv2, "findHomography", lambda *args, **kwargs: (matrix, np.ones((4, 1)))
    )
    with pytest.raises(ValueError):
        geometry.compute_homography(RECTANGLE, RECTANGLE)
