"""SYNTHETIC TESTS — these numerical answers are not real model accuracy."""

from dataclasses import replace

import numpy as np
import pytest

from app.evaluation.coordinates import (
    error_summary,
    evaluate_coordinates,
    landmark_errors,
)
from app.evaluation.detection import average_precision, evaluate_detection
from app.evaluation.metrics import assign, iou_matrix
from app.evaluation.schemas import Clip, ClipData, FileRef, Frame, Landmark, Observation
from app.evaluation.teams import evaluate_teams
from app.evaluation.tracking import evaluate_tracking

BOX = (1.0, 1.0, 9.0, 15.0)
BOX_B = (21.0, 1.0, 29.0, 15.0)


def observation(
    frame=0, identity="1", box=BOX, team="team_a", confidence=0.9, **kwargs
):
    return Observation(
        frame, frame / 10, box, identity, team, confidence=confidence, **kwargs
    )


def clip_data(gt, predictions, frames=(0,), **kwargs):
    reference = FileRef(path="synthetic-only", sha256="0" * 64)
    clip = Clip(
        clip_id="synthetic",
        video=reference,
        frames=reference,
        annotations=reference,
        fps=10,
        frame_count=100,
        duration_seconds=10,
        width=200,
        height=100,
        football_format="5v5",
        conditions="SYNTHETIC TEST ONLY",
        pitch_length_metres=40,
        pitch_width_metres=20,
        team_mapping={"team_a": "team_a", "team_b": "team_b"},
        team_mapping_basis="Declared synthetic colors, fixed before scoring",
        independent_pitch_ground_truth=True,
        pitch_ground_truth_method="Analytic test fixture",
    )
    return ClipData(
        clip,
        [Frame(i, i / 10, True) for i in frames],
        gt,
        detections=predictions,
        tracks=predictions,
        **kwargs,
    )


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((0, 0, 10, 10), (0, 0, 10, 10), 1),
        ((0, 0, 10, 10), (10, 10, 20, 20), 0),
        ((0, 0, 10, 10), (5, 0, 15, 10), 1 / 3),
    ],
)
def test_known_iou(a, b, expected):
    assert iou_matrix([a], [b])[0, 0] == pytest.approx(expected)


def test_gated_assignment_maximizes_valid_matches_before_iou():
    matches = assign(np.array([[0.9, 0.5], [0.5, 0.49]]), 0.5)
    assert {(a, b) for a, b, _ in matches} == {(0, 1), (1, 0)}
    assert len({a for a, _, _ in matches}) == len({b for _, b, _ in matches}) == 2


@pytest.mark.parametrize(
    "gt,pred,expected",
    [
        ([], [], (0, 0, 0, None, None, None)),
        ([observation()], [], (0, 0, 1, None, 0, 0)),
        ([], [observation()], (0, 1, 0, 0, None, 0)),
        (
            [observation()],
            [observation(), observation(identity="2")],
            (1, 1, 0, 0.5, 1, 2 / 3),
        ),
    ],
)
def test_detection_counts_empty_frames_and_duplicates(gt, pred, expected):
    result = evaluate_detection([clip_data(gt, pred)])
    for key, value in zip(
        ("tp", "fp", "fn", "precision", "recall", "f1"), expected, strict=True
    ):
        assert result[key] == (pytest.approx(value) if value is not None else None)


def test_empty_reviewed_frame_false_positives_are_counted():
    result = evaluate_detection(
        [
            clip_data(
                [observation()], [observation(), observation(frame=1)], frames=(0, 1)
            )
        ]
    )
    assert (result["annotated_frames"], result["tp"], result["fp"], result["fn"]) == (
        2,
        1,
        1,
        0,
    )


def test_ignored_officials_and_partial_visible_boxes():
    gt = [
        observation(box=(0, 0, 4, 8)),
        observation(identity="official", box=BOX_B, team="official"),
    ]
    predictions = [observation(box=(0, 0, 4, 8)), observation(identity="2", box=BOX_B)]
    result = evaluate_detection([clip_data(gt, predictions)])
    assert (
        result["tp"],
        result["fp"],
        result["fn"],
        result["ignored_predictions"],
    ) == (1, 0, 0, 1)


def test_ap50_known_ranked_predictions_and_missing_recall():
    gt = [observation(), observation(identity="2", box=BOX_B)]
    pred = [
        observation(confidence=0.9),
        observation(identity="3", confidence=0.8),
        observation(identity="2", box=BOX_B, confidence=0.7),
    ]
    assert average_precision([clip_data(gt, pred)]) == pytest.approx(5 / 6)
    assert average_precision([clip_data(gt, pred[:1])]) == pytest.approx(0.5)
    assert average_precision([clip_data(gt, [])]) == 0
    assert average_precision([clip_data([], [])]) is None


def test_tracking_standard_metrics_for_switch():
    gt = [observation(frame=i) for i in range(3)]
    pred = [observation(frame=i, identity="10" if i < 2 else "11") for i in range(3)]
    overall, per_clip = evaluate_tracking([clip_data(gt, pred, frames=(0, 1, 2))])
    assert overall["idf1"] == pytest.approx(2 / 3)
    assert overall["mota"] == pytest.approx(2 / 3)
    assert overall["motp"] == 0
    assert overall["num_switches"] == 1
    assert overall["num_false_positives"] == overall["num_misses"] == 0
    assert per_clip["synthetic"]["num_unique_objects"] == 1


def test_ap_matching_prioritizes_confidence_before_ignored_regions():
    gt = [
        observation(box=(0, 0, 10, 10)),
        observation(identity="official", box=(3, 0, 13, 10), team="official"),
    ]
    predictions = [
        observation(box=(3, 0, 13, 10), confidence=0.9),
        observation(box=(100, 0, 110, 10), confidence=0.8),
        observation(box=(0, 0, 10, 10), confidence=0.7),
    ]
    # The highest-confidence box validly matches the player. It must not be
    # discarded by the confidence-independent Hungarian assignment for counts.
    assert average_precision([clip_data(gt, predictions)]) == 1


def test_tracking_gap_and_clip_local_ids():
    first = clip_data(
        [observation(frame=i) for i in range(3)],
        [observation(frame=i, identity="10") for i in (0, 2)],
        frames=(0, 1, 2),
    )
    second = clip_data([observation()], [observation(identity="10")])
    second.clip = second.clip.model_copy(update={"clip_id": "second"})
    overall, rows = evaluate_tracking([first, second])
    assert rows["synthetic"]["idf1"] == pytest.approx(0.8)
    assert rows["synthetic"]["num_misses"] == 1
    assert rows["synthetic"]["num_fragmentations"] == 1
    assert rows["synthetic"]["num_switches"] == 0
    assert overall["num_unique_objects"] == 2
    assert overall["idf1"] == pytest.approx(6 / 7)
    assert overall["mota"] == pytest.approx(0.75)


def test_motp_is_iou_distance_and_no_gt_is_not_perfect_accuracy():
    result, _ = evaluate_tracking(
        [
            clip_data(
                [observation(box=(0, 0, 10, 10))], [observation(box=(2, 0, 12, 10))]
            )
        ]
    )
    assert result["motp"] == pytest.approx(1 / 3)
    empty, _ = evaluate_tracking([clip_data([], [])])
    assert empty["idf1"] is None and empty["mota"] is None and empty["motp"] is None


def test_automatic_team_metrics_include_unknown_and_missing_tracks():
    boxes = [(i * 20.0, 0.0, i * 20.0 + 10, 20.0) for i in range(4)]
    gt = [
        observation(identity=str(i + 1), box=box, team="team_a" if i < 2 else "team_b")
        for i, box in enumerate(boxes)
    ]
    pred = [
        observation(identity=str(10 + i), box=box) for i, box in enumerate(boxes[:3])
    ]
    clip = clip_data(
        gt, pred, automatic_teams={"10": "team_a", "11": "unknown", "12": "team_a"}
    )
    result = evaluate_teams([clip])
    assert result["accuracy"] == 0.25
    assert (
        result["accuracy_among_classified"]
        == result["coverage"]
        == result["unknown_rate"]
        == 0.5
    )
    assert result["associated_tracks"] == 3
    assert result["per_class"]["team_a"] == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "support": 2,
    }
    assert result["per_class"]["team_b"]["recall"] == 0
    assert result["confusion_matrix"] == {
        "team_a": {"team_a": 1, "team_b": 0, "unknown": 1},
        "team_b": {"team_a": 1, "team_b": 0, "unknown": 1},
    }


def test_team_mapping_is_explicit_and_gt_unknown_is_excluded():
    clip = clip_data(
        [observation(), observation(identity="2", box=BOX_B, team="unknown")],
        [observation(identity="10")],
        automatic_teams={"10": "team_b"},
    )
    assert evaluate_teams([clip])["accuracy"] == 0
    clip.clip = clip.clip.model_copy(
        update={"team_mapping": {"team_a": "team_b", "team_b": "team_a"}}
    )
    result = evaluate_teams([clip])
    assert result["accuracy"] == 1 and result["eligible_tracks"] == 1


def test_coordinate_error_5_metres_aggregates_and_missing_pairs():
    summary = error_summary([0, 5, 10])
    assert summary["mean"] == summary["median"] == 5
    assert summary["rmse"] == pytest.approx(np.sqrt(125 / 3))
    assert summary["max"] == 10 and summary["p95"] is None
    assert error_summary(list(range(20)))["p95"] == pytest.approx(18.05)
    clip = clip_data(
        [
            observation(pitch=(10, 10)),
            observation(identity="2", box=BOX_B, pitch=(20, 10)),
        ],
        [],
    )
    clip.coordinates = [observation(pitch=(13, 14))]
    result = evaluate_coordinates([clip])["player_coordinates"]
    assert result["mean"] == result["rmse"] == 5
    assert (
        result["ground_truth_positions"] == 2
        and result["unmatched_ground_truth_positions"] == 1
    )
    assert error_summary([])["mean"] is None


def test_homography_error_uses_held_out_points_not_fit_residuals():
    clip = clip_data([], [])
    clip.landmarks = [
        Landmark(str(i), image, pitch, "fit")
        for i, (image, pitch) in enumerate(
            zip(
                [(0, 0), (100, 0), (100, 100), (0, 100)],
                [(0, 0), (10, 0), (10, 10), (0, 10)],
                strict=True,
            )
        )
    ]
    clip.landmarks += [Landmark("held-out", (50, 50), (8, 9), "validation")]
    assert landmark_errors(clip) == pytest.approx([5])
    clip.landmarks[-1] = replace(clip.landmarks[-1], pitch=(5, 5))
    assert landmark_errors(clip) == pytest.approx([0], abs=1e-6)


def test_known_projective_mapping_on_separate_validation_points():
    from app.cv.homography import transform_points

    known = np.array([[0.1, 0.02, 1], [0.01, 0.15, 2], [0.001, 0.002, 1]])
    fit = [(0, 0), (100, 0), (100, 100), (0, 100)]
    held_out = [(30, 20), (80, 70)]
    clip = clip_data([], [])
    for role, points in (("fit", fit), ("validation", held_out)):
        clip.landmarks.extend(
            Landmark(f"{role}-{i}", point, truth, role)
            for i, (point, truth) in enumerate(
                zip(points, transform_points(points, known), strict=True)
            )
        )
    assert landmark_errors(clip) == pytest.approx([0, 0], abs=1e-5)
