"""Explicit synthetic jersey fixtures; no weights, detector or tracker execution."""

import csv
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.team_classifier import (
    Appearance,
    aggregate_appearance,
    classify_tracks,
    jersey_crop,
    jersey_feature,
)
from app.cv.team_pipeline import ClassificationError, classify_tracking
from app.services.tracking_artifacts import COLUMNS


def color_sample(bgr, quality=1.0):
    color = jersey_feature(np.full((40, 30, 3), bgr, dtype=np.uint8)).color
    return Appearance(color, quality)


def test_jersey_crop_excludes_head_legs_and_grass(settings):
    image = np.full((200, 120, 3), (0, 180, 0), dtype=np.uint8)
    image[37:81, 36:84] = (0, 0, 255)
    crop = jersey_crop(image, (20, 15, 100, 135), settings)
    assert crop.shape == (44, 48, 3)
    assert np.all(crop == (0, 0, 255))
    assert jersey_feature(crop).quality == 1


@pytest.mark.parametrize(
    "box",
    [
        (),
        (1, 2, 3),
        (20, 20, 20, 90),
        (80, 2, 30, 80),
        (-80, 2, -1, 80),
        (101, 1, 120, 80),
        (1, 101, 80, 140),
        (1, 1, 3, 4),
        (1, float("nan"), 80, 80),
        (1, 1, float("inf"), 80),
        ("bad", 0, 80, 80),
        None,
    ],
)
def test_invalid_crops_are_skipped(settings, box):
    assert jersey_crop(np.zeros((100, 100, 3), np.uint8), box, settings) is None


@pytest.mark.parametrize(
    "image",
    [
        None,
        np.empty((0, 0, 3), np.uint8),
        np.zeros((50, 50), np.uint8),
        np.zeros((50, 50, 4), np.uint8),
        np.zeros((50, 50, 3), np.float32),
    ],
)
def test_invalid_frame_cannot_produce_jersey_evidence(settings, image):
    assert jersey_crop(image, (0, 0, 40, 40), settings) is None
    assert jersey_feature(image) is None


def test_partial_torso_is_clipped_to_image_bounds(settings):
    image = np.full((100, 100, 3), (0, 0, 255), np.uint8)
    crop = jersey_crop(image, (-40, -50, 120, 200), settings)
    assert crop is not None and crop.shape == (87, 88, 3)
    assert np.all(crop == (0, 0, 255))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_features_or_quality_cannot_produce_confident_result(settings, value):
    good = color_sample((0, 0, 255))
    assert aggregate_appearance([Appearance((value, 0, 0), 1)] * 3, settings) is None
    assert aggregate_appearance([Appearance(good.color, value)] * 3, settings) is None


def test_multiframe_evidence_required_and_color_switches_are_uncertain(settings):
    red, blue = color_sample((0, 0, 255)), color_sample((255, 0, 0))
    assert aggregate_appearance([red], settings) is None
    assert aggregate_appearance([red, red], settings) is None
    stable = aggregate_appearance([red] * 3, settings)
    mixed = aggregate_appearance([red, blue, red, blue], settings)
    assert stable.quality == 1 and mixed.quality == 0
    result = classify_tracks(
        {1: [red] * 3, 2: [blue] * 3, 3: [red, blue, red, blue], 4: []}, settings
    )
    assert [p.team for p in result] == [
        TrackTeam.TEAM_B,
        TrackTeam.TEAM_A,
        TrackTeam.UNKNOWN,
        TrackTeam.UNKNOWN,
    ]


def test_cluster_mapping_is_deterministic_under_track_and_sample_reordering(settings):
    red, blue = color_sample((0, 0, 255)), color_sample((255, 0, 0))
    evidence = {7: [red] * 4, 1: [blue] * 3, 9: [red] * 3, 2: [blue] * 5}
    expected = classify_tracks(evidence, settings)
    assert {p.track_id: p.team for p in expected} == {
        1: "team_a",
        2: "team_a",
        7: "team_b",
        9: "team_b",
    }
    for _ in range(3):
        assert (
            classify_tracks(dict(reversed(list(evidence.items()))), settings)
            == expected
        )
    assert all(p.confidence == 1 for p in expected)


def test_similar_jerseys_do_not_force_two_teams(settings):
    evidence = {1: [color_sample((0, 0, 255))] * 3, 2: [color_sample((5, 5, 250))] * 3}
    assert all(p.team == "unknown" for p in classify_tracks(evidence, settings))
    assert classify_tracks({1: evidence[1]}, settings)[0].team == "unknown"
    assert classify_tracks({}, settings) == []


def test_confidence_threshold_and_poor_crops(settings):
    red, blue = color_sample((0, 0, 255), 0.75), color_sample((255, 0, 0), 0.75)
    evidence = {1: [red] * 3, 2: [blue] * 3}
    result = classify_tracks(evidence, settings)
    assert all(
        p.team != "unknown" and p.confidence == pytest.approx(0.75) for p in result
    )
    settings.team_unknown_threshold = 0.8
    assert all(p.team == "unknown" for p in classify_tracks(evidence, settings))
    crop = np.zeros((40, 40, 3), np.uint8)
    crop[:20] = (0, 0, 255)
    crop[20:] = (255, 0, 0)
    assert jersey_feature(crop).quality < 0.6


def test_ambiguous_intermediate_color_stays_unknown(settings):
    red = color_sample((0, 0, 255))
    blue = color_sample((255, 0, 0))
    middle = Appearance(
        tuple((r + b) / 2 for r, b in zip(red.color, blue.color, strict=True)), 1
    )
    evidence = {i: [red if i < 10 else blue] * 3 for i in range(20)}
    evidence[99] = [middle] * 3
    results = {p.track_id: p for p in classify_tracks(evidence, settings)}
    assert results[0].team != results[10].team
    assert results[99].team == "unknown" and results[99].confidence < 0.6


def write_tracks(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def pipeline_fixture(tmp_path, rows, count, stride=1):
    path = tmp_path / "tracks.csv"
    write_tracks(path, rows)
    detection = SimpleNamespace(
        decoded_frames=count,
        processed_frames=len(range(0, count, stride)),
        frame_stride=stride,
        frame_width=160,
        frame_height=200,
    )
    tracking = SimpleNamespace(
        total_track_rows=len(rows), unique_tracks=len({row[2] for row in rows})
    )
    return path, detection, tracking


def synthetic_frame(_number):
    image = np.zeros((200, 160, 3), np.uint8)
    image[:, :80] = (0, 0, 255)
    image[:, 80:] = (255, 0, 0)
    return image


def test_pipeline_streams_frames_once_respects_interval_and_cap(tmp_path, settings):
    settings.team_sample_interval = 2
    settings.team_max_samples_per_track = 3
    rows = [
        (frame, frame / 10, track, left, 0, left + 70, 190, 0.9)
        for frame in range(10)
        for track, left in ((3, 0), (7, 85))
    ]
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 10)
    load, progress = Mock(side_effect=synthetic_frame), Mock()
    result = classify_tracking(
        path, detection, tracking, 1.0, settings, load_frame=load, progress=progress
    )
    assert [call.args[0] for call in load.call_args_list] == [0, 4, 8]
    assert (result.processed_frames, result.sampled_frames, result.valid_samples) == (
        10,
        3,
        6,
    )
    assert {p.team for p in result.predictions} == {"team_a", "team_b"}
    assert result.diagnostics["attempted_crops"] == 10
    assert result.diagnostics["rejected_small_or_outside_crops"] == 0
    assert result.diagnostics["eligible_tracks"] == 2
    assert result.diagnostics["cluster_separation_lab"] > 20
    assert [call.args for call in progress.call_args_list] == [
        (i, 10) for i in range(1, 11)
    ]


def test_invalid_boxes_and_short_tracks_have_unknown_assignments(tmp_path, settings):
    settings.team_sample_interval = 1
    rows = [(frame, frame / 10, 1, -1, 0, 10, 20, 0.9) for frame in range(4)]
    rows.append((3, 0.3, 2, 0, 0, 70, 190, 0.9))
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 4)
    load = Mock(side_effect=synthetic_frame)
    result = classify_tracking(
        path, detection, tracking, 1, settings, load_frame=load, progress=Mock()
    )
    assert load.call_count == 1
    assert result.diagnostics["attempted_crops"] == 5
    assert result.diagnostics["rejected_small_or_outside_crops"] == 4
    assert result.diagnostics["insufficient_sample_tracks"] == 2
    assert [p.team for p in result.predictions] == ["unknown", "unknown"]


def test_one_bad_crop_does_not_abort_other_samples(tmp_path, settings, monkeypatch):
    settings.team_sample_interval = 1
    rows = [
        (frame, frame / 10, track, left, 0, left + 70, 190, 0.9)
        for frame in range(5)
        for track, left in ((3, 0), (7, 85))
    ]
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 5)
    original = cv2.cvtColor
    calls = 0

    def sometimes_bad(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise cv2.error("synthetic crop conversion failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(cv2, "cvtColor", sometimes_bad)
    result = classify_tracking(
        path,
        detection,
        tracking,
        1,
        settings,
        load_frame=synthetic_frame,
        progress=Mock(),
    )
    assert result.valid_samples == 9
    assert {p.team for p in result.predictions} == {"team_a", "team_b"}


def test_empty_sampled_frames_have_progress_without_decoding(tmp_path, settings):
    path, detection, tracking = pipeline_fixture(tmp_path, [], 6, stride=2)
    load, progress = Mock(), Mock()
    result = classify_tracking(
        path, detection, tracking, 1, settings, load_frame=load, progress=progress
    )
    assert result.predictions == [] and result.processed_frames == 3
    load.assert_not_called()
    assert progress.call_args.args == (3, 3)


@pytest.mark.parametrize(
    "rows",
    [
        [(0, float("nan"), 1, 0, 0, 70, 190, 0.9)],
        [(0, -1, 1, 0, 0, 70, 190, 0.9)],
        [(0, 1, 1, 0, 0, 70, 190, 0.9)],
        [(0, 0, 0, 0, 0, 70, 190, 0.9)],
        [(0, 0, 1, 0, 0, 70, 190, 0.9)] * 2,
        [(2, 0.2, 1, 0, 0, 70, 190, 0.9), (0, 0, 1, 0, 0, 70, 190, 0.9)],
    ],
)
def test_corrupt_tracking_metadata_fails_safely(tmp_path, settings, rows):
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 4)
    with pytest.raises(ClassificationError, match="tracking CSV"):
        classify_tracking(
            path,
            detection,
            tracking,
            1,
            settings,
            load_frame=synthetic_frame,
            progress=Mock(),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"team_sample_interval": 0},
        {"team_max_samples_per_track": 2},
        {"team_unknown_threshold": float("nan")},
        {"team_min_crop_width": 0},
        {"team_min_samples": 1},
        {"team_min_samples": 30, "team_max_samples_per_track": 20},
    ],
)
def test_invalid_team_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_diagnostic_observation_does_not_change_predictions(settings):
    red, blue = color_sample((0, 0, 255)), color_sample((255, 0, 0))
    evidence = {1: [red] * 3, 2: [blue] * 3, 3: [red], 4: [red, blue, red, blue]}
    audit = {}
    assert classify_tracks(evidence, settings) == classify_tracks(
        evidence, settings, diagnostics=audit
    )
    assert audit["insufficient_sample_tracks"] == 1
    assert audit["inconsistent_evidence_tracks"] == 1
    assert audit["eligible_tracks"] == 2
    assert audit["low_margin_tracks"] == 0


def test_tiny_early_crops_do_not_exhaust_later_valid_sample_budget(tmp_path, settings):
    settings.team_sample_interval = 1
    settings.team_max_samples_per_track = 3
    rows = [
        (frame, frame / 10, 1, 0, 0, 3 if frame < 5 else 70, 190, 0.9)
        for frame in range(10)
    ]
    path, detection, tracking = pipeline_fixture(tmp_path, rows, 10)
    load = Mock(side_effect=synthetic_frame)
    result = classify_tracking(
        path, detection, tracking, 1, settings, load_frame=load, progress=Mock()
    )
    assert [call.args[0] for call in load.call_args_list] == [5, 7, 9]
    assert result.valid_samples == 3
    assert result.diagnostics["rejected_small_or_outside_crops"] == 5
    assert result.diagnostics["budget_skipped_crops"] == 2
