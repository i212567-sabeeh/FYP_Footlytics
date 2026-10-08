"""Synthetic geometry and streaming coordinate checks, reusing Phase 5 transforms."""

from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from test_team_classifier import pipeline_fixture

from app.cv import coordinate_pipeline, homography
from app.cv.coordinate_pipeline import CoordinateMappingError, map_tracking
from app.cv.player_position import (
    PITCH_TOLERANCE_METRES,
    bottom_center,
    inside_pitch,
    map_ground_points,
)


def test_bottom_center_uses_foot_contact_not_torso():
    assert bottom_center((10, 20, 30, 80)) == (20, 80)
    assert bottom_center((-30, -20, -10, -1)) == (-20, -1)
    assert bottom_center((1e308, 0, 1.6e308, 10)) == (1.3e308, 10)


@pytest.mark.parametrize(
    "box",
    [
        None,
        (),
        (1, 2, 3),
        (1, 2, 3, 4, 5),
        (30, 20, 10, 80),
        (10, 80, 30, 20),
        (10, 20, 10, 80),
        (10, 20, 30, 20),
        (float("nan"), 0, 20, 40),
        (0, 0, float("inf"), 40),
        (0, -float("inf"), 20, 40),
        ("10", "20", "30", "80"),
    ],
)
def test_malformed_boxes_are_rejected_without_repair(box):
    with pytest.raises(ValueError, match="finite, ordered"):
        bottom_center(box)


@pytest.mark.parametrize(
    "point,expected",
    [
        ((0, 0), True),
        ((30, 20), True),
        ((15, 10), True),
        ((-3.2, 10), False),
        ((10, -1), False),
        ((30.01, 10), False),
        ((10, 20.01), False),
        ((-5e-7, 10), True),
        ((30 + 5e-7, 20 + 5e-7), True),
        ((-2e-6, 10), False),
    ],
)
def test_pitch_bounds_have_small_absolute_tolerance(point, expected):
    assert inside_pitch(*point, 30, 20) is expected


@pytest.mark.parametrize(
    "point", [(float("nan"), 0), (0, float("inf")), (-float("inf"), 0)]
)
def test_nonfinite_positions_are_rejected(point):
    with pytest.raises(ValueError, match="finite"):
        inside_pitch(*point, 30, 20)


@pytest.mark.parametrize(
    "dimensions", [(0, 20), (30, -1), (float("nan"), 20), (30, float("inf"))]
)
def test_invalid_dimensions_are_rejected_even_without_points(dimensions):
    with pytest.raises(ValueError):
        map_ground_points([], np.eye(3), *dimensions)


def test_identity_preserves_outside_values_without_clamping():
    points = [(0, 0), (30, 20), (-3.2, 10), (40, 22), (-PITCH_TOLERANCE_METRES / 2, 0)]
    result = map_ground_points(points, np.eye(3), 30, 20)
    assert [(p.pitch_x, p.pitch_y) for p in result] == points
    assert [p.inside_pitch for p in result] == [True, True, False, False, True]


def test_scaled_transform_uses_length_x_width_y_and_match_dimensions():
    point = bottom_center((100, 50, 300, 200))
    result = map_ground_points([point], np.diag([0.1, 0.2, 1]), 60, 40)[0]
    assert (result.pixel_x, result.pixel_y, result.pitch_x, result.pitch_y) == (
        200,
        200,
        20,
        40,
    )
    assert result.inside_pitch
    assert not map_ground_points([point], np.diag([0.1, 0.2, 1]), 30, 20)[
        0
    ].inside_pitch


def test_known_correspondences_reuse_phase5_fitting_and_transform(monkeypatch):
    images = [(0, 0), (500, 0), (500, 300), (0, 300)]
    pitch = [(0, 0), (30, 0), (30, 20), (0, 20)]
    fit = Mock(wraps=cv2.findHomography)
    transform = Mock(wraps=cv2.perspectiveTransform)
    reuse = Mock(wraps=homography.transform_points)
    monkeypatch.setattr(cv2, "findHomography", fit)
    monkeypatch.setattr(cv2, "perspectiveTransform", transform)
    matrix = homography.compute_homography(images, pitch)
    monkeypatch.setattr(homography, "transform_points", reuse)
    result = map_ground_points(images, matrix, 30, 20)
    fit.assert_called_once()
    reuse.assert_called_once()
    assert transform.call_count >= 1
    assert np.allclose([(p.pitch_x, p.pitch_y) for p in result], pitch)
    assert all(p.inside_pitch for p in result)


@pytest.mark.parametrize(
    "transformed",
    [None, [(1, 2, 3)], [(1, 2), (3, 4)], [(float("nan"), 0)], [(0, float("inf"))]],
)
def test_invalid_transform_output_is_rejected(monkeypatch, transformed):
    monkeypatch.setattr(homography, "transform_points", lambda *_: transformed)
    with pytest.raises(ValueError, match="invalid pitch coordinates"):
        map_ground_points([(10, 20)], np.eye(3), 30, 20)


def test_projective_horizon_fails_clearly():
    with pytest.raises(ValueError, match="horizon"):
        map_ground_points([(10, 20)], [[1, 0, 0], [0, 1, 0], [0.1, 0, -1]], 30, 20)


def test_streaming_multiple_tracks_skips_invalid_boxes_and_reports_real_rows(
    tmp_path, monkeypatch
):
    rows = [
        (0, 0, 3, 10, 20, 30, 80, 0.9),
        (0, 0, 7, -5, 0, -1, 10, 0.8),
        (1, 0.1, 3, 12, 20, 32, 80, 0.9),
        (2, 0.2, 9, 5, 0, 5, 10, 0.7),
        (3, 0.3, 7, 20, 0, 30, 10, 0.8),
    ]
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 4)
    monkeypatch.setattr(coordinate_pipeline, "MAPPING_BATCH_ROWS", 2)
    write, progress = Mock(), Mock()
    reuse = Mock(wraps=homography.transform_points)
    monkeypatch.setattr(homography, "transform_points", reuse)
    run = map_tracking(
        path,
        detection,
        tracking,
        1,
        np.diag([1, 0.1, 1]),
        30,
        20,
        write_position=write,
        progress=progress,
    )
    assert (run.total_rows, run.valid_mapped_rows, run.skipped_invalid_boxes) == (
        5,
        4,
        1,
    )
    assert (run.inside_pitch_rows, run.outside_pitch_rows, run.unique_tracks) == (
        3,
        1,
        2,
    )
    assert (run.first_frame, run.last_frame) == (0, 3)
    assert [c.args for c in progress.call_args_list] == [(2, 5), (4, 5), (5, 5)]
    assert [c.args[0].track_id for c in write.call_args_list] == [3, 7, 3, 7]
    assert all(len(c.args[0]) <= 2 for c in reuse.call_args_list)
    assert write.call_args_list[1].args[1].pitch_x == -3


def test_empty_tracking_has_no_fabricated_positions(tmp_path):
    path, detection, tracking = pipeline_fixture(tmp_path, [], 4)
    write, progress = Mock(), Mock()
    run = map_tracking(
        path,
        detection,
        tracking,
        1,
        np.eye(3),
        30,
        20,
        write_position=write,
        progress=progress,
    )
    assert run.total_rows == run.valid_mapped_rows == run.unique_tracks == 0
    assert run.first_frame is run.last_frame is None
    write.assert_not_called()
    progress.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["timestamp", "track_id", "duplicate", "truncated", "bad_box"]
)
def test_metadata_corruption_fails_but_invalid_box_is_counted(tmp_path, fault):
    rows = [(0, 0, 1, 10, 0, 30, 40, 0.9), (1, 0.1, 1, 10, 0, 30, 40, 0.9)]
    if fault == "timestamp":
        rows[1] = (1, float("nan"), *rows[1][2:])
    elif fault == "track_id":
        rows[1] = (1, 0.1, 0, *rows[1][3:])
    elif fault == "duplicate":
        rows[1] = rows[0]
    elif fault == "bad_box":
        rows[1] = (1, 0.1, 1, "bad", 0, 30, 40, 0.9)
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 2)
    if fault == "truncated":
        tracking.total_track_rows = 3
    options = dict(write_position=Mock(), progress=Mock())
    if fault == "bad_box":
        result = map_tracking(
            path, detection, tracking, 1, np.eye(3), 30, 20, **options
        )
        assert result.skipped_invalid_boxes == 1 and result.valid_mapped_rows == 1
    else:
        with pytest.raises(CoordinateMappingError):
            map_tracking(path, detection, tracking, 1, np.eye(3), 30, 20, **options)
