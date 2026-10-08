"""Deterministic geometry, snapshot semantics, bounded regrouping and finite output."""

import math
from collections import defaultdict

import pytest
from pydantic import ValidationError
from test_player_analytics import point, provenance, saved_trajectories

from app.analytics import team_rows
from app.analytics.team import calculate_teams, snapshot
from app.analytics.trajectory_rows import (
    AnalyticsError,
    CleanObservation,
    read_trajectories,
)
from app.core.config import Settings
from app.schemas.team_analytics import TeamSnapshot


def calculate(points, assignments=None, minimum=3):
    output = defaultdict(list)
    progress = []
    run = calculate_teams(
        sorted(points, key=lambda p: (p.frame, p.track_id)),
        assignments or {p.track_id: "team_a" for p in points},
        minimum,
        sum(p.clean is not None for p in points),
        write=lambda name, row: output[name].append(row),
        progress=lambda *value: progress.append(value),
    )
    return run, output, progress


def test_centroid_and_axis_definitions():
    row = snapshot(4, 0.2, "team_a", [(10, 10), (20, 20), (30, 30)], 3)
    assert (row.centroid_x, row.centroid_y) == (20, 20)
    row = snapshot(4, 0.2, "team_a", [(10, 5), (25, 15), (40, 25)], 3)
    assert row.width_metres == 20 and row.depth_metres == 30
    assert row.bounding_box_area_m2 == 600


def test_compactness_and_unique_pairwise_spacing():
    row = snapshot(0, 0, "team_a", [(0, 0), (3, 4)], 2)
    assert row.mean_pairwise_distance_metres == 5
    assert row.compactness_radius_metres == 2.5
    triangle = snapshot(0, 0, "team_a", [(0, 0), (4, 0), (0, 3)], 3)
    assert triangle.mean_pairwise_distance_metres == 4  # (3 + 4 + 5) / 3
    assert triangle.compactness_radius_metres == pytest.approx(
        (5 + math.sqrt(73) + math.sqrt(52)) / 9
    )


@pytest.mark.parametrize(
    "positions,area",
    [
        ([(0, 0), (10, 0), (10, 10), (0, 10)], 100),
        ([(0, 0), (1, 1), (2, 2)], None),
        ([(0, 0), (1, 1)], None),
        ([(2, 2)] * 3, None),
    ],
)
def test_hull_area_and_degeneracy(positions, area):
    assert snapshot(0, 0, "team_a", positions, 2).convex_hull_area_m2 == area


@pytest.mark.parametrize("count", [0, 1, 2])
def test_insufficient_visibility_has_count_but_no_geometry(count):
    row = snapshot(0, 0, "team_a", [(i, i) for i in range(count)], 3)
    assert not row.sufficient_players and row.visible_players == count
    assert all(
        value is None
        for key, value in row.model_dump().items()
        if key
        not in {
            "frame_number",
            "timestamp_seconds",
            "team",
            "visible_players",
            "sufficient_players",
        }
    )


def test_separate_teams_unknown_excluded_and_centroid_distance():
    points = [
        point(0, 0, 0, track=1),
        point(0, 2, 0, track=2),
        point(0, 3, 4, track=3),
        point(0, 5, 4, track=4),
        point(0, 99, 99, track=5),
    ]
    _, output, _ = calculate(
        points, {1: "team_a", 2: "team_a", 3: "team_b", 4: "team_b", 5: "unknown"}, 2
    )
    a, b = output["team_tactics_frames"]
    assert (a.centroid_x, a.centroid_y, b.centroid_x, b.centroid_y) == (1, 0, 4, 4)
    assert a.visible_players == b.visible_players == 2
    assert (
        a.centroid_distance_to_opponent_metres
        == b.centroid_distance_to_opponent_metres
        == 5
    )


def test_snapshot_averages_ignore_gaps_and_insufficient_values_and_keep_segments():
    points = [
        point(0, 0, track=1),
        point(0, 4, track=2),
        point(0.1, 1, track=1),  # one player: not width zero
        point(100, 10, track=1, segment=2),
        point(100, 18, track=2, segment=2),
        point(100, None, track=3),
    ]
    run, output, progress = calculate(points, minimum=2)
    a, b = run.teams
    assert a.valid_snapshots == 2 and a.insufficient_snapshots == 1
    assert a.avg_depth_metres == 6 and a.avg_centroid_x == 8
    assert a.avg_visible_players == 2 and b.avg_depth_metres is None
    assert run.observed_frames == 3 and progress[-1] == (5, 5)
    assert [
        r.timestamp_seconds for r in output["team_tactics_frames"] if r.team == "team_a"
    ] == [0, 0.1, 100]


def test_frame_key_never_merges_similar_timestamps():
    rows = [point(1, 1, track=1, frame=10), point(1.0000001, 2, track=2, frame=11)]
    run, output, _ = calculate(rows, minimum=2)
    assert run.observed_frames == 2 and run.teams[0].valid_snapshots == 0
    assert [r.visible_players for r in output["team_tactics_frames"]] == [1, 0, 1, 0]


@pytest.mark.parametrize(
    "rows",
    [
        [point(0, 1, track=1), point(0, 2, track=1)],
        [point(0, 1, track=1), point(0.1, 2, track=2, frame=0)],
    ],
)
def test_duplicate_tracks_or_conflicting_frame_timestamp_fail(rows):
    with pytest.raises(AnalyticsError):
        calculate(rows, minimum=2)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_positions_rejected(value):
    with pytest.raises(AnalyticsError):
        snapshot(0, 0, "team_a", [(value, 0), (1, 1)], 2)


@pytest.mark.parametrize(
    "field",
    [
        "width_metres",
        "depth_metres",
        "compactness_radius_metres",
        "mean_pairwise_distance_metres",
        "convex_hull_area_m2",
        "bounding_box_area_m2",
    ],
)
@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_invalid_metrics_cannot_be_persisted(field, value):
    data = snapshot(0, 0, "team_a", [(0, 0), (3, 4)], 2).model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        TeamSnapshot.model_validate(data)


@pytest.mark.parametrize("value", [0, 1, 23])
def test_visibility_setting_is_validated(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tactics_min_players_per_team=value)


def test_external_regroup_uses_clean_only_and_merges_bounded_runs(
    tmp_path, monkeypatch
):
    points = [
        point(t / 10, track + t, track=track, frame=t)
        for track in range(1, 5)
        for t in range(8)
    ]
    source = tmp_path / "trajectory.csv"
    saved_trajectories(source, points)  # fixture raw coordinates are deliberately 999
    monkeypatch.setattr(team_rows, "SORT_CHUNK_ROWS", 2)
    monkeypatch.setattr(team_rows, "MERGE_FAN_IN", 2)
    ordered = list(
        team_rows.ordered_snapshots(
            read_trajectories(source, provenance(points), 8, 1, 1),
            tmp_path,
            len(points),
            lambda *_: None,
        )
    )
    assert [(p.frame, p.track_id) for p in ordered] == [
        (f, t) for f in range(8) for t in range(1, 5)
    ]
    assert all(p.clean[0] == p.track_id + p.frame for p in ordered)
    run, _, _ = calculate(ordered)
    assert run.teams[0].avg_depth_metres == 3


@pytest.mark.parametrize("points", [[], [CleanObservation(0, 0, 1, None, None)]])
def test_empty_and_all_rejected_produce_explicit_empty_summaries(points):
    run, output, _ = calculate(points)
    assert run.observed_frames == 0 and not output["team_tactics_frames"]
    assert all(t.valid_snapshots == 0 and t.avg_width_metres is None for t in run.teams)
