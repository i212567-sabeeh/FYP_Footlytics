# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Measure movement KPIs on cached real tracks; no YOLO, DB writes or benchmark GT.

Maps cached ByteTrack boxes with a saved calibration (read from a temporary copy
of the database), then runs the unchanged cleaning and player-analytics code at
each requested cadence. Coarser cadences subsample the same tracks, so their
differences come from sampling and position noise, not from other identities.
Run from the repository root. The output directory must be new.
"""

import argparse
import csv
import json
import math
import shutil
import sqlite3
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.analytics.player import calculate_players
from app.analytics.trajectory_rows import CleanObservation
from app.core.config import Settings
from app.cv.coordinate_rows import CoordinateObservation
from app.cv.player_position import bottom_center, map_ground_points
from app.cv.trajectory import clean_track

MAD_TO_SIGMA = 1.4826


def load_calibration(database: Path, match_id: int) -> dict:
    """Read one saved calibration from a temporary copy; never open the original."""
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "calibration-source.sqlite3"
        shutil.copy2(database, copy)
        with sqlite3.connect(f"file:{copy}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT id, video_id, updated_at, image_width, image_height, "
                "pitch_length_metres, pitch_width_metres, reprojection_error, "
                "homography_matrix FROM pitch_calibrations WHERE match_id = ?",
                (match_id,),
            ).fetchone()
    if row is None:
        raise SystemExit(f"No calibration exists for match {match_id}.")
    keys = (
        "id",
        "video_id",
        "updated_at",
        "image_width",
        "image_height",
        "length",
        "width",
        "reprojection_error",
        "matrix",
    )
    calibration = dict(zip(keys, row, strict=True))
    calibration["matrix"] = json.loads(calibration["matrix"])
    return calibration


def read_tracks(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return [
            {
                "frame": int(row["frame_number"]),
                "timestamp": float(row["timestamp_seconds"]),
                "track": int(row["track_id"]),
                "box": tuple(float(row[key]) for key in ("x1", "y1", "x2", "y2")),
                "confidence": float(row["confidence"]),
            }
            for row in csv.DictReader(stream)
        ]


def quantiles(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)

    def at(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]

    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "p90": at(0.90),
        "p99": at(0.99),
        "max": ordered[-1],
    }


def run_cadence(rows: list[dict], stride: int, calibration: dict, settings: Settings):
    length, width = calibration["length"], calibration["width"]
    selected = [row for row in rows if row["frame"] % stride == 0]
    positions = map_ground_points(
        [bottom_center(row["box"]) for row in selected],
        calibration["matrix"],
        length,
        width,
    )
    observations = sorted(
        (
            CoordinateObservation(
                number,
                row["frame"],
                row["timestamp"],
                row["track"],
                row["box"],
                row["confidence"],
                (position.pixel_x, position.pixel_y),
                (position.pitch_x, position.pitch_y),
                position.inside_pitch,
            )
            for number, (row, position) in enumerate(
                zip(selected, positions, strict=True), 1
            )
        ),
        key=lambda item: (item.track_id, item.timestamp, item.frame, item.source_row),
    )
    cleaned = []
    for _, track in groupby(observations, key=lambda item: item.track_id):
        cleaned.extend(clean_track(track, settings, length, width))
    outputs = defaultdict(list)
    source = SimpleNamespace(
        pitch_length_metres=length,
        pitch_width_metres=width,
        max_plausible_speed_mps=settings.trajectory_max_plausible_speed_mps,
        max_gap_seconds=settings.trajectory_max_gap_seconds,
        source_rows=len(cleaned),
    )
    calculate_players(
        (
            CleanObservation(
                point.raw.frame,
                point.raw.timestamp,
                point.raw.track_id,
                point.segment_id,
                point.clean,
            )
            for point in cleaned
        ),
        source,
        settings,
        write=lambda kind, model: outputs[kind].append(model),
        progress=lambda *_: None,
    )
    return cleaned, outputs


def summarise(cleaned, outputs, settings: Settings, stride: int) -> dict:
    players = outputs["players"]
    intervals = outputs["intervals"]
    active = math.fsum(p.active_duration_seconds for p in players)
    distance = math.fsum(p.total_distance_metres for p in players)
    fast = math.fsum(
        i.dt_seconds
        for i in intervals
        if i.speed_mps >= settings.player_sprint_speed_threshold_mps
    )
    maxima = [p.max_speed_mps for p in players if p.max_speed_mps is not None]
    raw, smooth = defaultdict(list), defaultdict(list)
    for point in cleaned:
        if point.usable:
            raw[point.raw.track_id].append((point.raw.frame, point.raw.pitch))
            smooth[point.raw.track_id].append((point.raw.frame, point.clean))
    summary = {
        "frame_stride": stride,
        "observations": len(cleaned),
        "statuses": dict(Counter(point.status for point in cleaned)),
        "tracks": len(players),
        "tracks_with_valid_intervals": sum(p.valid_interval_count > 0 for p in players),
        "valid_intervals": len(intervals),
        "excluded_intervals": sum(p.excluded_interval_count for p in players),
        "active_seconds": active,
        "distance_metres": distance,
        "pooled_speed_mps": distance / active if active else None,
        "interval_speed_mps": quantiles([i.speed_mps for i in intervals]),
        "time_at_or_above_sprint_threshold_seconds": fast,
        "time_fraction_at_or_above_sprint_threshold": fast / active if active else None,
        "sprint_events": len(outputs["sprints"]),
        "sprint_distance_metres": math.fsum(
            s.distance_metres for s in outputs["sprints"]
        ),
        "track_max_speed_mps": quantiles(maxima),
        "tracks_with_max_speed_at_least_9_mps": sum(value >= 9 for value in maxima),
        "tracks_with_max_speed_at_least_10_mps": sum(value >= 10 for value in maxima),
    }
    if stride == 1:
        summary["position_noise_raw"] = pooled_noise(list(raw.values()))
        summary["position_noise_after_cleaning"] = pooled_noise(list(smooth.values()))
    return summary


def pooled_noise(tracks: list[list[tuple[int, tuple[float, float]]]]) -> dict:
    """Robust per-axis position noise from second differences of consecutive frames.

    For independent noise s per axis, x[i+1] - 2x[i] + x[i-1] has standard
    deviation s*sqrt(6); real acceleration adds only a*dt^2 (millimetres at
    25 Hz). Second differences from every track are pooled before the median.
    """
    combined = {"triplets": 0, "x": [], "y": []}
    for points in tracks:
        triplets = zip(points, points[1:], points[2:], strict=False)
        for (f0, p0), (f1, p1), (f2, p2) in triplets:
            if f1 - f0 == 1 and f2 - f1 == 1:
                combined["triplets"] += 1
                combined["x"].append(abs(p2[0] - 2 * p1[0] + p0[0]))
                combined["y"].append(abs(p2[1] - 2 * p1[1] + p0[1]))
    if not combined["triplets"]:
        return {"triplets": 0, "sigma_x_metres": None, "sigma_y_metres": None}
    scale = MAD_TO_SIGMA / math.sqrt(6)
    return {
        "triplets": combined["triplets"],
        "sigma_x_metres": scale * statistics.median(combined["x"]),
        "sigma_y_metres": scale * statistics.median(combined["y"]),
    }


def matched_ratio(per_track: dict, fine: int, coarse: int, minimum: float) -> dict:
    """Same-track average speed at the fine cadence divided by the coarse one."""
    ratios = []
    for metrics in per_track.values():
        a, b = metrics.get(fine), metrics.get(coarse)
        if (
            a
            and b
            and min(a.active_duration_seconds, b.active_duration_seconds) >= minimum
            and b.total_distance_metres > 0
        ):
            ratios.append(a.average_speed_mps / b.average_speed_mps)
    return {
        "definition": f"average speed at stride {fine} / stride {coarse}, "
        f"tracks with >= {minimum} s active at both",
        **(quantiles(ratios) or {"count": 0}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--strides", type=int, nargs="+", default=[1, 5])
    parser.add_argument("--min-active-seconds", type=float, default=2.0)
    parser.add_argument(
        "--speed-windows",
        type=float,
        nargs="+",
        default=[0.0],
        help="PLAYER_SPEED_WINDOW_SECONDS values to compare (0 = every pair)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    # Defaults only: no .env secrets are loaded and analytics settings match the
    # application defaults that the deployment uses unchanged.
    base = Settings(_env_file=None)
    calibration = load_calibration(args.database, args.match_id)
    rows = read_tracks(args.tracks)
    results = {
        "inputs": {
            "tracks": str(args.tracks),
            "rows": len(rows),
            "calibration": {k: v for k, v in calibration.items() if k != "matrix"},
            "settings": {
                key: getattr(base, key)
                for key in (
                    "trajectory_max_plausible_speed_mps",
                    "trajectory_max_gap_seconds",
                    "trajectory_smoothing_window",
                    "trajectory_smoothing_max_shift_metres",
                    "player_sprint_speed_threshold_mps",
                    "player_sprint_min_duration_seconds",
                )
            },
        },
        "speed_windows": {},
    }
    with (args.output / "tracks.csv").open("x", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(
            ["speed_window_seconds", "track_id", "frame_stride", "active_seconds"]
            + ["distance_metres", "average_speed_mps", "max_speed_mps", "sprint_count"]
        )
        for window in args.speed_windows:
            settings = base.model_copy(update={"player_speed_window_seconds": window})
            result = results["speed_windows"][str(window)] = {"cadences": {}}
            per_track = defaultdict(dict)
            for stride in args.strides:
                cleaned, outputs = run_cadence(rows, stride, calibration, settings)
                result["cadences"][str(stride)] = summarise(
                    cleaned, outputs, settings, stride
                )
                for player in outputs["players"]:
                    per_track[player.track_id][stride] = player
            if len(args.strides) >= 2:
                result["matched_speed_ratio"] = matched_ratio(
                    per_track, args.strides[0], args.strides[1], args.min_active_seconds
                )
            for track, metrics in sorted(per_track.items()):
                for stride, player in sorted(metrics.items()):
                    writer.writerow(
                        [
                            window,
                            track,
                            stride,
                            player.active_duration_seconds,
                            player.total_distance_metres,
                            player.average_speed_mps,
                            player.max_speed_mps,
                            player.sprint_count,
                        ]
                    )
    (args.output / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
