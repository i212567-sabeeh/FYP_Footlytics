"""Deterministic scientific checks using saved cleaned positions only."""

import csv
import json
from collections import defaultdict

import pytest
from pydantic import ValidationError

from app.analytics.player import calculate_players
from app.analytics.trajectory_rows import (
    AnalyticsError,
    CleanObservation,
    read_trajectories,
)
from app.core.config import Settings
from app.schemas.trajectories import TrajectorySummary
from app.services.trajectory_artifacts import COLUMNS


def point(t, x, y=0, *, track=1, segment=1, frame=None):
    return CleanObservation(
        round(t * 10) if frame is None else frame,
        t,
        track,
        segment if x is not None else None,
        (x, y) if x is not None else None,
    )


def provenance(points, *, length=100, width=50, **changes):
    usable = sum(p.clean is not None for p in points)
    return TrajectorySummary(
        **{
            "source_rows": len(points),
            "usable_rows": usable,
            "rejected_rows": len(points) - usable,
            "outside_pitch_rows": len(points) - usable,
            "jump_outlier_rows": 0,
            "invalid_temporal_rows": 0,
            "interpolated_rows": 0,
            "smoothed_rows": 0,
            "unique_tracks": len({p.track_id for p in points}),
            "segments": len(
                {(p.track_id, p.segment_id) for p in points if p.clean is not None}
            ),
            "first_frame": min((p.frame for p in points), default=None),
            "last_frame": max((p.frame for p in points), default=None),
            "coordinate_job_id": 1,
            "coordinate_attempt": 0,
            "pitch_length_metres": length,
            "pitch_width_metres": width,
            "max_plausible_speed_mps": 12,
            "max_gap_seconds": 2,
            "smoothing_window": 1,
            "smoothing_max_shift_metres": 0,
            **changes,
        }
    )


def saved_trajectories(path, points):
    """Explicit synthetic Phase 10 fixture; raw coordinates differ from clean."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for index, p in enumerate(points, 1):
            row = dict.fromkeys(COLUMNS, "")
            row.update(
                source_row_number=index,
                frame_number=p.frame,
                timestamp_seconds=p.timestamp,
                track_id=p.track_id,
                segment_id=p.segment_id,
                x1=0,
                y1=0,
                x2=10,
                y2=10,
                confidence=0.9,
                pixel_x=5,
                pixel_y=10,
                raw_pitch_x=999,
                raw_pitch_y=999,
                inside_pitch="true" if p.clean else "false",
                usable="true" if p.clean else "false",
                status="accepted" if p.clean else "outside_pitch",
                is_interpolated="false",
            )
            if p.clean is not None:
                row.update(clean_pitch_x=p.clean[0], clean_pitch_y=p.clean[1])
            writer.writerow(row)


def calculate(points, settings, *, source=None, **config):
    output = defaultdict(list)
    updates = []
    settings = settings.model_copy(update=config)
    run = calculate_players(
        iter(points),
        source or provenance(points),
        settings,
        write=lambda name, row: output[name].append(row),
        progress=lambda done, total: updates.append((done, total)),
    )
    for rows in output.values():
        for row in rows:
            json.dumps(row.model_dump(), allow_nan=False)
    return output, run, updates


def test_simple_distance_and_speed_units(settings):
    output, run, _ = calculate([point(0, 0), point(1, 3, 4)], settings)
    row = output["players"][0]
    assert row.total_distance_metres == 5
    assert row.active_duration_seconds == 1
    assert row.average_speed_mps == row.max_speed_mps == 5
    assert row.average_speed_kmh == row.max_speed_kmh == 18
    assert run.valid_intervals == 1


def test_irregular_time_uses_distance_over_duration_not_sample_mean(settings):
    points = [point(0, 0), point(1, 3, 4), point(3, 3, 8)]
    output, _, _ = calculate(points, settings)
    row = output["players"][0]
    assert row.total_distance_metres == 9 and row.active_duration_seconds == 3
    assert row.average_speed_mps == 3 and row.average_speed_kmh == pytest.approx(10.8)
    assert row.max_speed_mps == 5
    assert [p.speed_mps for p in output["intervals"]] == [5, 2]


def test_segment_spatial_jump_and_long_time_gap_excluded(settings):
    points = [
        point(0, 0),
        point(1, 3, 4),
        point(10, 50, 30, segment=2),
        point(11, 53, 34, segment=2),
    ]
    output, _, _ = calculate(points, settings)
    row = output["players"][0]
    assert row.total_distance_metres == 10 and row.active_duration_seconds == 2
    assert row.segment_count == 2
    assert sum(p.occupancy_seconds for p in output["heatmaps"]) == 2


def test_rejection_breaks_same_segment_continuity(settings):
    output, _, _ = calculate(
        [point(0, 0), point(0.5, None), point(1, 4), point(2, 6)], settings
    )
    assert output["players"][0].total_distance_metres == 2
    assert output["players"][0].active_duration_seconds == 1
    assert len(output["intervals"]) == 1


@pytest.mark.parametrize(
    "points",
    [
        [point(0, 0), point(0, 1, frame=1)],
        [point(1, 0), point(0, 1)],
        [point(0, 0), point(1, 1, frame=0)],
        [point(0, 0), point(3, 1)],
        [point(0, 0), point(1, 13)],
    ],
)
def test_invalid_intervals_have_no_speed_duration_or_heatmap(settings, points):
    output, run, _ = calculate(points, settings)
    row = output["players"][0]
    assert row.average_speed_mps is None and row.max_speed_mps is None
    assert row.total_distance_metres == row.active_duration_seconds == 0
    assert run.excluded_intervals == 1 and not output["heatmaps"]


def test_saved_cleaning_limits_are_authoritative(settings):
    points = [point(0, 0), point(1, 8)]
    output, run, _ = calculate(
        points,
        settings,
        source=provenance(points, max_plausible_speed_mps=7),
        trajectory_max_plausible_speed_mps=20,
    )
    assert run.excluded_intervals == 1 and output["players"][0].max_speed_mps is None


def test_duration_qualified_sprint_and_maximum(settings):
    points = [point(0, 0), point(0.5, 4), point(1.5, 14)]
    output, _, _ = calculate(points, settings)
    sprint = output["sprints"][0]
    assert sprint.duration_seconds == 1.5 and sprint.distance_metres == 14
    assert (
        sprint.max_speed_mps == 10
        and sprint.start_timestamp == 0
        and sprint.end_timestamp == 1.5
    )
    row = output["players"][0]
    assert row.sprint_count == 1 and row.sprint_distance_metres == 14
    assert row.sprint_duration_seconds == 1.5 and row.max_speed_mps == 10


def test_short_burst_is_threshold_interval_but_not_sprint(settings):
    output, _, _ = calculate([point(0, 0), point(0.5, 4)], settings)
    assert output["intervals"][0].above_sprint_threshold
    assert output["players"][0].sprint_count == 0 and not output["sprints"]


def test_two_sprints_separated_by_normal_movement(settings):
    points = [point(0, 0), point(1, 8), point(2, 10), point(3, 18)]
    output, _, _ = calculate(points, settings)
    assert output["players"][0].sprint_count == 2
    assert [(s.start_timestamp, s.end_timestamp) for s in output["sprints"]] == [
        (0, 1),
        (2, 3),
    ]


@pytest.mark.parametrize("break_kind", ["segment", "rejected", "gap"])
def test_fast_sequences_cannot_combine_across_discontinuities(settings, break_kind):
    points = [point(0, 0), point(0.5, 4)]
    if break_kind == "rejected":
        points += [point(0.6, None), point(0.7, 5), point(1.2, 9)]
    elif break_kind == "segment":
        points += [point(0.6, 5, segment=2), point(1.1, 9, segment=2)]
    else:
        points += [point(5, 5), point(5.5, 9)]
    output, _, _ = calculate(points, settings)
    assert not output["sprints"] and output["players"][0].sprint_count == 0


def test_configurable_sprint_threshold_inclusive_and_min_duration(settings):
    points = [point(0, 0), point(0.5, 3)]
    output, _, _ = calculate(
        points,
        settings,
        player_sprint_speed_threshold_mps=6,
        player_sprint_min_duration_seconds=0.5,
    )
    assert output["players"][0].sprint_count == 1


@pytest.mark.parametrize("length,width", [(10, 10), (30, 20)])
def test_time_weighted_heatmap_uses_match_grid_and_interval_start(
    settings, length, width
):
    points = [point(0, 1, 1), point(1, 6, 1), point(3, 6, 8)]
    output, _, _ = calculate(
        points,
        settings,
        source=provenance(points, length=length, width=width),
        player_heatmap_bins_x=2,
        player_heatmap_bins_y=2,
    )
    cells = output["heatmaps"]
    assert sum(c.occupancy_seconds for c in cells) == 3
    assert sum(c.occupancy_fraction for c in cells) == pytest.approx(1)
    if length == 10:
        assert [(c.x_bin, c.y_bin, c.occupancy_seconds) for c in cells] == [
            (0, 0, 1),
            (1, 0, 2),
        ]
    else:
        assert len(cells) == 1 and cells[0].occupancy_seconds == 3
    assert cells[0].x_max == length / 2 and cells[0].y_max == width / 2


def test_heatmap_maximum_pitch_boundary_is_final_cell(settings):
    points = [point(0, 10, 10), point(1, 10, 10)]
    output, _, _ = calculate(
        points,
        settings,
        source=provenance(points, length=10, width=10),
        player_heatmap_bins_x=2,
        player_heatmap_bins_y=2,
    )
    assert (output["heatmaps"][0].x_bin, output["heatmaps"][0].y_bin) == (1, 1)
    assert output["players"][0].average_speed_mps == 0


@pytest.mark.parametrize("points", [[], [point(0, None)], [point(0, 1)]])
def test_empty_or_short_tracks_are_unavailable_not_invented(settings, points):
    output, run, _ = calculate(points, settings)
    assert not output["intervals"] and not output["sprints"] and not output["heatmaps"]
    assert run.valid_intervals == 0
    if points:
        row = output["players"][0]
        assert (
            row.total_distance_metres
            == row.active_duration_seconds
            == row.sprint_count
            == 0
        )
        assert row.average_speed_mps is None and row.max_speed_mps is None
        assert (row.first_timestamp is None) == (points[0].clean is None)


def test_multiple_tracks_independent(settings):
    points = [point(0, 0), point(1, 8), point(0, 50, track=2), point(2, 54, track=2)]
    output, _, updates = calculate(points, settings)
    a, b = output["players"]
    assert (a.total_distance_metres, b.total_distance_metres) == (8, 4)
    assert (a.active_duration_seconds, b.active_duration_seconds) == (1, 2)
    assert (a.sprint_count, b.sprint_count) == (1, 0)
    assert updates[-1] == (4, 4)


def test_streaming_does_not_buffer_an_entire_track(settings):
    consumed = written = 0

    def observations():
        nonlocal consumed
        for index in range(10000):
            consumed += 1
            assert consumed - written <= 2
            yield point(index / 10, 1, frame=index)

    def write(name, _row):
        nonlocal written
        if name == "intervals":
            written += 1

    run = calculate_players(
        observations(),
        provenance([point(0, 1)]),
        settings,
        write=write,
        progress=lambda *_: None,
    )
    assert run.valid_intervals == 9999


def test_reader_uses_clean_positions_only(tmp_path, settings):
    points = [point(0, 0), point(1, 3, 4)]
    path = tmp_path / "clean.csv"
    saved_trajectories(path, points)
    rows = list(read_trajectories(path, provenance(points), 20, 1, 2))
    output, _, _ = calculate(rows, settings)
    assert output["players"][0].total_distance_metres == 5


def test_phase10_statuses_and_boundary_tolerance_are_preserved(tmp_path, settings):
    points = [point(0, -5e-7, 0), point(1, 1, 0), point(2, 2, 0)]
    path = tmp_path / "clean.csv"
    saved_trajectories(path, points)
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["status"], rows[1]["status"] = "segment_start", "smoothed"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    source = provenance(points, smoothed_rows=1)
    output, _, _ = calculate(
        list(read_trajectories(path, source, 30, 1, 3)), settings, source=source
    )
    assert output["players"][0].total_distance_metres == pytest.approx(2 + 5e-7)
    assert output["intervals"][0].start_x == -5e-7
    assert output["heatmaps"][0].x_bin == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("clean_pitch_x", "nan"),
        ("clean_pitch_y", "inf"),
        ("clean_pitch_x", ""),
        ("clean_pitch_x", "-1"),
        ("segment_id", "0"),
        ("track_id", "-1"),
        ("usable", "false"),
        ("status", "jump_outlier"),
        ("timestamp_seconds", "nan"),
        ("is_interpolated", "true"),
        ("frame_number", "100"),
    ],
)
def test_invalid_cleaned_rows_fail_safely(tmp_path, field, value):
    points = [point(0, 1)]
    path = tmp_path / "clean.csv"
    saved_trajectories(path, points)
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0][field] = value
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AnalyticsError, match="invalid or unavailable"):
        list(read_trajectories(path, provenance(points), 20, 1, 2))


@pytest.mark.parametrize("fault", ["missing", "empty", "truncated", "unordered"])
def test_reader_rejects_missing_or_inconsistent_artifact(tmp_path, fault):
    points = [point(0, 1), point(1, 2)]
    path = tmp_path / "clean.csv"
    if fault == "empty":
        path.write_text("")
    elif fault == "truncated":
        saved_trajectories(path, points[:1])
    elif fault == "unordered":
        saved_trajectories(path, points[::-1])
    with pytest.raises(AnalyticsError):
        list(read_trajectories(path, provenance(points), 20, 1, 2))


@pytest.mark.parametrize(
    "field,value",
    [
        ("player_sprint_speed_threshold_mps", 0),
        ("player_sprint_speed_threshold_mps", float("nan")),
        ("player_sprint_min_duration_seconds", 0),
        ("player_sprint_min_duration_seconds", float("inf")),
        ("player_heatmap_bins_x", 0),
        ("player_heatmap_bins_y", 101),
    ],
)
def test_invalid_analytics_settings_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
