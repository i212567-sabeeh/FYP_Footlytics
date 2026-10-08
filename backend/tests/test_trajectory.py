"""Synthetic trajectory quality, real CSV sorting and bounded processing tests."""

import csv
from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import Mock

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.cv import coordinate_rows, trajectory
from app.cv.coordinate_rows import CoordinateObservation, TrajectoryError
from app.cv.trajectory import clean_track
from app.cv.trajectory_pipeline import clean_coordinates
from app.schemas.coordinates import CoordinateSummary
from app.schemas.trajectories import TrajectorySummary
from app.services.coordinate_artifacts import COLUMNS
from app.services.trajectory_artifacts import TrajectoryArtifact


def observation(t, x=5, y=10, *, track=1, frame=None, source_row=None):
    number = round(max(0, t) * 10) if frame is None else frame
    # Saved synthetic calibration is X=0.5*pixel_x, Y=0.5*pixel_y.
    pixel = (2 * x, 2 * y)
    return CoordinateObservation(
        source_row or number + 1,
        number,
        t,
        track,
        (pixel[0] - 2, pixel[1] - 10, pixel[0] + 2, pixel[1]),
        0.9,
        pixel,
        (x, y),
        0 <= x <= 100 and 0 <= y <= 50,
    )


def clean(rows, **options):
    return list(clean_track(iter(rows), Settings(_env_file=None, **options), 100, 50))


def test_straight_path_keeps_true_positions_track_and_segment():
    result = clean([observation(t, 5 + t) for t in range(5)])
    assert all(p.usable and p.raw.track_id == 1 and p.segment_id == 1 for p in result)
    assert [p.clean for p in result] == [(5 + t, 10) for t in range(5)]
    assert not any(p.status == "jump_outlier" for p in result)


def test_jitter_reduction_is_quantitative_and_endpoints_preserved():
    rows = [observation(i / 10, 5 + i / 10, 10 + (-1) ** i * 0.2) for i in range(9)]
    result = clean(rows)
    raw_error = np.sqrt(np.mean([(p.pitch[1] - 10) ** 2 for p in rows]))
    clean_error = np.sqrt(np.mean([(p.clean[1] - 10) ** 2 for p in result]))
    assert clean_error < raw_error * 0.6
    assert result[0].clean == rows[0].pitch and result[-1].clean == rows[-1].pitch
    assert np.allclose([p.clean[0] for p in result], [p.pitch[0] for p in rows])
    assert sum(p.status == "smoothed" for p in result) == 7


def test_irregular_timestamps_preserve_constant_motion():
    times = [0, 0.05, 0.9, 1.5, 1.95]
    rows = [observation(t, 5 + 2 * t, frame=i) for i, t in enumerate(times)]
    assert [p.clean for p in clean(rows)] == [p.pitch for p in rows]


def test_direction_change_is_retained_with_bounded_shift():
    points = [(5, 10), (6, 10), (7, 10), (7, 11), (7, 12)]
    result = clean([observation(t, *p) for t, p in enumerate(points)])
    assert result[0].clean == points[0] and result[-1].clean == points[-1]
    assert max(np.linalg.norm(np.subtract(p.clean, p.raw.pitch)) for p in result) <= 0.5
    assert result[1].clean[0] < result[2].clean[0]
    assert result[2].clean[1] < result[3].clean[1]


def test_isolated_teleport_is_rejected_and_later_observations_recover():
    points = [(5, 10), (6, 10), (40, 30), (8, 10), (9, 10)]
    result = clean([observation(t, *p) for t, p in enumerate(points)])
    assert result[2].status == "jump_outlier" and result[2].clean is None
    assert result[2].raw.pitch == (40, 30) and not result[2].usable
    assert [p.clean for p in result[3:]] == points[3:]
    assert {p.segment_id for p in result if p.usable} == {1}


def test_persistent_discontinuity_starts_new_segment_without_connecting_jump():
    result = clean([observation(t, x) for t, x in enumerate([5, 6, 40, 41, 42])])
    assert all(p.usable for p in result)
    assert [p.segment_id for p in result] == [1, 1, 2, 2, 2]
    assert result[2].status == "segment_start"


def test_outside_position_keeps_raw_values_and_null_clean_coordinates():
    result = clean([observation(0, -2)])[0]
    assert result.raw.pitch == (-2, 10)
    assert not result.usable and result.clean is None and result.segment_id is None
    assert result.status == "outside_pitch"


def test_long_gap_creates_segments_and_short_gaps_are_not_filled():
    rows = [observation(t, 5 + t) for t in (0, 0.1, 0.3, 0.4, 4, 4.1)]
    result = clean(rows)
    assert len(result) == len(rows)
    assert [p.raw.timestamp for p in result] == [p.timestamp for p in rows]
    assert [p.segment_id for p in result] == [1, 1, 1, 1, 2, 2]
    assert result[3].clean == rows[3].pitch and result[4].clean == rows[4].pitch


@pytest.mark.parametrize(
    "times,frames",
    [
        ([0, 0, 1], [0, 1, 2]),
        ([0, 0.1, 1], [0, 0, 2]),
        ([0, 0.1, 1], [2, 1, 3]),
    ],
)
def test_temporal_conflicts_are_retained_and_break_continuity(times, frames):
    result = clean(
        [observation(t, frame=f) for t, f in zip(times, frames, strict=True)]
    )
    assert result[1].status == "invalid_temporal" and result[1].clean is None
    assert result[0].segment_id == 1 and result[2].segment_id == 2


def test_negative_timestamp_is_unusable_without_poisoning_later_data():
    result = clean([observation(-1), observation(0), observation(1)])
    assert result[0].status == "invalid_temporal" and not result[0].usable
    assert result[0].raw.timestamp == -1
    assert all(p.usable for p in result[1:])


def test_configured_thresholds_change_quality_decisions_and_smoothing():
    rows = [observation(t, x) for t, x in enumerate([5, 6, 40, 8, 9])]
    assert clean(rows)[2].status == "jump_outlier"
    assert all(p.usable for p in clean(rows, trajectory_max_plausible_speed_mps=100))
    normal = [observation(t, 5 + t) for t in range(5)]
    assert (
        len({p.segment_id for p in clean(normal, trajectory_max_gap_seconds=0.5)}) == 5
    )
    jitter = [observation(i / 10, 5, 10 + (-1) ** i * 0.2) for i in range(5)]
    assert [p.clean for p in clean(jitter, trajectory_smoothing_window=1)] == [
        p.pitch for p in jitter
    ]
    limited = clean(jitter, trajectory_smoothing_max_shift_metres=0.05)
    assert all(
        np.linalg.norm(np.subtract(p.clean, p.raw.pitch)) <= 0.050000001
        for p in limited
    )


@pytest.mark.parametrize("window", [1, 3, 5, 11])
@pytest.mark.parametrize("length", [1, 2, 3, 7, 15])
def test_smoothing_windows_keep_every_row_and_do_not_move_endpoints(window, length):
    rows = [observation(i / 10, 5 + i / 10) for i in range(length)]
    result = clean(rows, trajectory_smoothing_window=window)
    assert [p.raw for p in result] == rows
    assert result[0].clean == rows[0].pitch and result[-1].clean == rows[-1].pitch


@pytest.mark.parametrize(
    "name,value",
    [
        ("trajectory_max_plausible_speed_mps", 0),
        ("trajectory_max_plausible_speed_mps", float("inf")),
        ("trajectory_max_gap_seconds", -1),
        ("trajectory_max_gap_seconds", float("nan")),
        ("trajectory_smoothing_window", 0),
        ("trajectory_smoothing_window", 4),
        ("trajectory_smoothing_window", 13),
        ("trajectory_smoothing_max_shift_metres", -1),
        ("trajectory_smoothing_max_shift_metres", float("inf")),
    ],
)
def test_cleaning_settings_are_validated(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})


def coordinate_fixture(tmp_path, rows):
    path = tmp_path / "coordinates.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for p in rows:
            writer.writerow(
                (
                    p.frame,
                    p.timestamp,
                    p.track_id,
                    *p.box,
                    p.confidence,
                    *p.pixel,
                    *p.pitch,
                    "true" if p.inside_pitch else "false",
                )
            )
    summary = CoordinateSummary(
        total_rows=len(rows),
        valid_mapped_rows=len(rows),
        skipped_invalid_boxes=0,
        inside_pitch_rows=sum(r.inside_pitch for r in rows),
        outside_pitch_rows=sum(not r.inside_pitch for r in rows),
        unique_tracks=len({r.track_id for r in rows}),
        first_frame=min((r.frame for r in rows), default=None),
        last_frame=max((r.frame for r in rows), default=None),
        tracking_job_id=1,
        tracking_attempt=0,
        calibration_id=1,
        calibration_updated_at=datetime.now(UTC),
        pitch_length_metres=100,
        pitch_width_metres=50,
        bounds_tolerance_metres=1e-6,
    )
    return path, summary


def run_pipeline(tmp_path, rows, **kwargs):
    path, summary = coordinate_fixture(tmp_path, rows)
    original = path.read_bytes()
    output, progress = [], Mock()
    run = clean_coordinates(
        path,
        summary,
        1000,
        1,
        100,
        Settings(_env_file=None),
        tmp_path,
        write_observation=kwargs.get("write_observation", output.append),
        progress=progress,
    )
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("trajectory-*"))
    return run, output, progress


def test_external_sort_handles_unsorted_tracks_with_bounded_chunks_and_open_files(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(coordinate_rows, "SORT_CHUNK_ROWS", 3)
    monkeypatch.setattr(coordinate_rows, "MERGE_FAN_IN", 2)
    merge = Mock(wraps=coordinate_rows._merge)
    smooth = Mock(wraps=trajectory._smooth)
    monkeypatch.setattr(coordinate_rows, "_merge", merge)
    monkeypatch.setattr(trajectory, "_smooth", smooth)
    rows = [observation(i / 10, 5 + i / 10, track=t) for i in range(30) for t in (7, 3)]
    run, output, progress = run_pipeline(tmp_path, list(reversed(rows)))
    assert run.source_rows == run.usable_rows == 60 and run.unique_tracks == 2
    assert run.segments == 2
    assert [(p.raw.track_id, p.raw.timestamp) for p in output] == sorted(
        (p.track_id, p.timestamp) for p in rows
    )
    assert all(p.segment_id == 1 and p.clean == p.raw.pitch for p in output)
    assert len(merge.call_args_list) > 2
    assert max(len(c.args[0]) for c in merge.call_args_list) <= 2
    assert max(len(c.args[0]) for c in smooth.call_args_list) <= 3
    assert progress.call_args_list[-1].args == ("cleaning_tracks", 60, 60)


def test_multiple_tracks_are_independent_including_segment_ids(tmp_path):
    rows = [observation(t, x, track=3) for t, x in enumerate([5, 6, 40, 8, 9])]
    rows += [observation(t, 20 + t, track=7) for t in range(5)]
    run, output, _ = run_pipeline(tmp_path, rows)
    other = [p for p in output if p.raw.track_id == 7]
    assert [p.clean for p in other] == [(20 + t, 10) for t in range(5)]
    assert all(p.segment_id == 1 for p in other)
    assert run.jump_outlier_rows == 1 and run.segments == 2 and run.rejected_rows == 1


def test_empty_csv_yields_empty_summary(tmp_path):
    run, output, _ = run_pipeline(tmp_path, [])
    assert run.source_rows == run.usable_rows == run.segments == 0
    assert run.first_frame is run.last_frame is None and not output


def test_spooling_cleanup_on_write_failure_preserves_raw_csv(tmp_path):
    rows = [observation(t) for t in range(5)]
    with pytest.raises(OSError):
        run_pipeline(
            tmp_path, rows, write_observation=Mock(side_effect=OSError("full"))
        )
    assert not list(tmp_path.glob("trajectory-*"))
    assert len((tmp_path / "coordinates.csv").read_text().splitlines()) == 6


@pytest.mark.parametrize("fault", ["nan", "flag", "count", "header", "track_count"])
def test_corrupt_coordinate_input_fails_safely(tmp_path, fault):
    path, summary = coordinate_fixture(tmp_path, [observation(0)])
    if fault == "nan":
        path.write_text(path.read_text().replace("5,10,true", "nan,10,true"))
    elif fault == "flag":
        path.write_text(path.read_text().replace("true", "false"))
    elif fault == "header":
        path.write_text("private/bad/path\n")
    elif fault == "count":
        summary.valid_mapped_rows = 2
    else:
        summary.unique_tracks = 2
    with pytest.raises(TrajectoryError) as error:
        clean_coordinates(
            path,
            summary,
            1000,
            1,
            100,
            Settings(_env_file=None),
            tmp_path,
            write_observation=Mock(),
            progress=Mock(),
        )
    assert str(tmp_path) not in str(error.value)
    assert not list(tmp_path.glob("trajectory-*"))


def test_realistic_trajectory_artifact_smoke(tmp_path, record_property):
    # Explicit synthetic observations: no model, tracker, video decode or mapping.
    samples = [
        (0, 5, 10.2),
        (0.1, 5.1, 9.8),
        (0.2, 5.2, 10.2),
        (0.3, 40, 30),
        (0.4, 5.4, 10.2),
        (0.5, 5.5, 9.8),
        (0.6, 5.6, 10.2),
        (0.7, -2, 10),
        (3, 8, 10.2),
        (3.1, 8.1, 10),
    ]
    rows = [observation(t, x, y, track=3) for t, x, y in samples]
    rows += [observation(0, 20, 5, track=7), observation(0.1, 20.1, 5, track=7)]
    path, source = coordinate_fixture(tmp_path, rows)
    raw_bytes = path.read_bytes()
    settings = Settings(_env_file=None, storage_dir=tmp_path / "storage")
    with TrajectoryArtifact(settings, 1, 1, 1, 0) as artifact:
        run = clean_coordinates(
            path,
            source,
            1000,
            1,
            100,
            settings,
            artifact.path.parent,
            write_observation=artifact.write_observation,
            progress=Mock(),
        )
        data = TrajectorySummary(
            **asdict(run),
            coordinate_job_id=1,
            coordinate_attempt=0,
            pitch_length_metres=100,
            pitch_width_metres=50,
            max_plausible_speed_mps=settings.trajectory_max_plausible_speed_mps,
            max_gap_seconds=settings.trajectory_max_gap_seconds,
            smoothing_window=settings.trajectory_smoothing_window,
            smoothing_max_shift_metres=settings.trajectory_smoothing_max_shift_metres,
        )
        artifact.publish()
        artifact.keep()
    with artifact.path.open(encoding="utf-8", newline="") as stream:
        output = list(csv.DictReader(stream))
    assert len(output) == data.source_rows == 12
    assert data.usable_rows == 10 and data.rejected_rows == 2
    assert data.jump_outlier_rows == data.outside_pitch_rows == 1
    assert data.unique_tracks == 2 and data.segments == 3
    assert data.smoothed_rows == 2 and data.interpolated_rows == 0
    teleport, outside = output[3], output[7]
    assert teleport["raw_pitch_x"] == "40.0" and teleport["status"] == "jump_outlier"
    assert outside["raw_pitch_x"] == "-2.0" and outside["status"] == "outside_pitch"
    assert teleport["clean_pitch_x"] == outside["clean_pitch_y"] == ""
    assert [output[i]["segment_id"] for i in (0, 8, 10)] == ["1", "2", "1"]
    assert [float(output[i]["clean_pitch_y"]) for i in (1, 5)] == [10, 10]
    raw_error = np.sqrt(
        np.mean(
            [(float(output[i]["raw_pitch_y"]) - 10) ** 2 for i in (0, 1, 2, 4, 5, 6)]
        )
    )
    cleaned_error = np.sqrt(
        np.mean(
            [(float(output[i]["clean_pitch_y"]) - 10) ** 2 for i in (0, 1, 2, 4, 5, 6)]
        )
    )
    assert cleaned_error < raw_error
    assert path.read_bytes() == raw_bytes
    assert not list(settings.storage_dir.rglob("*.partial"))
    assert not list(settings.storage_dir.rglob("trajectory-*"))
    record_property(
        "trajectory_smoke",
        {
            "summary": data.model_dump(mode="json"),
            "rows": output,
            "raw_jitter_rmse_metres": float(raw_error),
            "cleaned_jitter_rmse_metres": float(cleaned_error),
        },
    )
