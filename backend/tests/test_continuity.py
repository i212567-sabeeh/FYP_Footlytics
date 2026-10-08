"""Small labelled fixtures for continuity reporting, never model inference."""

import csv

import pytest

from app.evaluation.continuity import continuity_metrics


def write(tmp_path, rows):
    path = tmp_path / "tracks.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frame_number", "timestamp_seconds", "track_id"])
        writer.writerows(rows)
    return path


def test_gaps_are_spans_not_observed_time(tmp_path):
    path = write(
        tmp_path, [(0, 0, 1), (0, 0, 2), (5, 0.2, 1), (20, 0.8, 1), (25, 1, 1)]
    )
    data = continuity_metrics(path, frame_stride=5, duration_seconds=60)
    assert data["unique_tracks"] == 2
    assert data["tracks_with_consecutive_observations"] == 1
    assert data["tracks_with_multiple_observations"] == 1
    assert data["longest_duration_seconds"] == 1
    assert data["median_duration_seconds"] == 0.5
    assert data["total_consecutively_observed_track_seconds"] == pytest.approx(0.4)
    assert data["very_short_tracks_under_2_seconds"] == 2
    assert data["new_ids_per_video_minute_proxy"] == 2


def test_empty_results_are_honest(tmp_path):
    data = continuity_metrics(write(tmp_path, []), frame_stride=1, duration_seconds=60)
    assert data["longest_duration_seconds"] is None
    assert data["mean_duration_seconds"] is None
    assert data["unique_tracks"] == 0


@pytest.mark.parametrize(
    "rows",
    [
        [(0, 0, 1), (0, 0, 1)],
        [(0, 0, 1), (1, 0, 1)],
        [(0, float("nan"), 1)],
        [(0, 0, -1)],
        [(1, 0.1, 1), (0, 0.2, 2)],
    ],
)
def test_invalid_observations_cannot_inflate_continuity(tmp_path, rows):
    with pytest.raises(ValueError):
        continuity_metrics(write(tmp_path, rows), frame_stride=1, duration_seconds=60)
