# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Known-truth movement KPI check: synthetic paths plus measured position noise.

Each scenario is an analytic trajectory with exact distance, maximum speed and
sprint count. Positions are sampled at the given frame rate, perturbed with
independent Gaussian noise (default: the per-axis noise measured on the real
60-second clip) and passed through the unchanged trajectory cleaning and player
analytics for each speed window. Synthetic results show estimator behaviour;
they are not football accuracy evidence. The output directory must be new.
"""

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.analytics.player import calculate_players
from app.analytics.trajectory_rows import CleanObservation
from app.core.config import Settings
from app.cv.coordinate_rows import CoordinateObservation
from app.cv.trajectory import clean_track

LENGTH, WIDTH = 105.0, 68.0
TRUTH_RATE = 1000  # Hz used to integrate the exact path length.


def speed_profile(phases):
    """Piecewise-linear speed: [(duration, start_speed, end_speed), ...]."""

    def speed(t):
        for duration, start, end in phases:
            if t <= duration:
                return start + (end - start) * t / duration
            t -= duration
        return phases[-1][2]

    return speed, sum(phase[0] for phase in phases)


def straight(origin, heading, profile):
    speed, total = speed_profile(profile)
    step = 1 / TRUTH_RATE
    samples, x, y = [(0.0, origin)], *origin
    for index in range(1, round(total * TRUTH_RATE) + 1):
        t = index * step
        travelled = speed(t - step / 2) * step
        x += math.cos(heading) * travelled
        y += math.sin(heading) * travelled
        samples.append((t, (x, y)))
    return samples, total, speed


def circle(centre, radius, metres_per_second, seconds):
    samples = []
    for index in range(round(seconds * TRUTH_RATE) + 1):
        t = index / TRUTH_RATE
        angle = metres_per_second * t / radius
        samples.append(
            (
                t,
                (
                    centre[0] + radius * math.cos(angle),
                    centre[1] + radius * math.sin(angle),
                ),
            )
        )
    return samples, seconds, lambda _t: metres_per_second


def zigzag(origin, metres_per_second, leg_seconds, legs):
    samples, (x, y), t = [(0.0, origin)], origin, 0.0
    for leg in range(legs):
        heading = math.pi / 4 if leg % 2 == 0 else -math.pi / 4
        for _ in range(round(leg_seconds * TRUTH_RATE)):
            t += 1 / TRUTH_RATE
            x += math.cos(heading) * metres_per_second / TRUTH_RATE
            y += math.sin(heading) * metres_per_second / TRUTH_RATE
            samples.append((t, (x, y)))
    return samples, leg_seconds * legs, lambda _t: metres_per_second


def sprint_events(speed, total, threshold, minimum):
    """Exact count of continuous above-threshold periods lasting at least minimum."""
    events, run, step = 0, 0.0, 1 / TRUTH_RATE
    for index in range(round(total * TRUTH_RATE)):
        if speed((index + 0.5) * step) >= threshold:
            run += step
        else:
            events += run + 1e-9 >= minimum
            run = 0.0
    return events + (run + 1e-9 >= minimum)


def scenarios(threshold, minimum):
    definitions = {
        "stationary_10s": straight((50, 34), 0, [(10, 0, 0)]),
        "walk_1.5mps_10s": straight((40, 30), 0.3, [(10, 1.5, 1.5)]),
        "jog_circle_3.5mps_r8m_10s": circle((52, 34), 8, 3.5, 10),
        "zigzag_4mps_90deg_turns_8s": zigzag((30, 30), 4, 1, 8),
        "sprint_8.5mps_profile_10s": straight(
            (20, 20),
            0.1,
            [(2, 3, 3), (1.5, 3, 8.5), (2, 8.5, 8.5), (1.5, 8.5, 3), (3, 3, 3)],
        ),
        "short_burst_7.5mps_0.6s": straight(
            (20, 40),
            -0.2,
            [(2, 3, 3), (0.3, 3, 7.5), (0.6, 7.5, 7.5), (0.3, 7.5, 3), (2, 3, 3)],
        ),
    }
    result = {}
    for name, (samples, total, speed) in definitions.items():
        steps = zip(samples, samples[1:], strict=False)
        path = math.fsum(math.dist(a[1], b[1]) for a, b in steps)
        peak = max(
            speed((index + 0.5) / TRUTH_RATE)
            for index in range(round(total * TRUTH_RATE))
        )
        result[name] = {
            "samples": samples,
            "seconds": total,
            "distance": path,
            "max_speed": peak,
            "sprints": sprint_events(speed, total, threshold, minimum),
        }
    return result


def observe(truth, fps, sigma, rng):
    """Sample the truth at each video frame and add independent Gaussian noise."""
    samples = truth["samples"]
    rows = []
    for frame in range(int(truth["seconds"] * fps + 1e-9) + 1):
        t = frame / fps
        position = samples[min(len(samples) - 1, round(t * TRUTH_RATE))][1]
        noisy = (
            position[0] + rng.gauss(0, sigma[0]),
            position[1] + rng.gauss(0, sigma[1]),
        )
        rows.append(
            CoordinateObservation(
                frame + 1,
                frame,
                t,
                1,
                (0.0, 0.0, 1.0, 1.0),
                0.9,
                (0.5, 1.0),
                noisy,
                True,
            )
        )
    return rows


def measure(rows, settings):
    outputs = defaultdict(list)
    cleaned = list(clean_track(iter(rows), settings, LENGTH, WIDTH))
    source = SimpleNamespace(
        pitch_length_metres=LENGTH,
        pitch_width_metres=WIDTH,
        max_plausible_speed_mps=settings.trajectory_max_plausible_speed_mps,
        max_gap_seconds=settings.trajectory_max_gap_seconds,
        source_rows=len(cleaned),
    )
    calculate_players(
        (
            CleanObservation(p.raw.frame, p.raw.timestamp, 1, p.segment_id, p.clean)
            for p in cleaned
        ),
        source,
        settings,
        write=lambda kind, model: outputs[kind].append(model),
        progress=lambda *_: None,
    )
    return outputs["players"][0]


def summary(values):
    return {
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--windows", type=float, nargs="+", default=[0, 0.12, 0.2, 0.32, 0.4]
    )
    parser.add_argument("--fps", type=float, nargs="+", default=[25])
    parser.add_argument("--sigma", type=float, nargs=2, default=[0.0198, 0.0528])
    parser.add_argument("--noise-scales", type=float, nargs="+", default=[0, 1, 2])
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = Settings(_env_file=None)
    truths = scenarios(
        base.player_sprint_speed_threshold_mps, base.player_sprint_min_duration_seconds
    )
    results = {
        "definitions": {
            "distance_error_percent": "100 * (measured - true) / true; "
            "absolute metres when true is 0",
            "noise": "independent Gaussian per axis and frame, scaled from --sigma",
            "truth": "exact analytic path integrated at 1000 Hz",
        },
        "truth": {
            name: {k: v for k, v in item.items() if k != "samples"}
            for name, item in truths.items()
        },
        "results": [],
    }
    for fps in args.fps:
        for scale in args.noise_scales:
            sigma = (args.sigma[0] * scale, args.sigma[1] * scale)
            for window in args.windows:
                settings = base.model_copy(
                    update={"player_speed_window_seconds": window}
                )
                for name, truth in truths.items():
                    distances, maxima, sprints, active = [], [], [], []
                    for seed in range(args.seeds if scale else 1):
                        rng = random.Random(f"{name}-{fps}-{scale}-{seed}")
                        player = measure(observe(truth, fps, sigma, rng), settings)
                        distances.append(player.total_distance_metres)
                        maxima.append(player.max_speed_mps or 0.0)
                        sprints.append(player.sprint_count)
                        active.append(player.active_duration_seconds)
                    error = [
                        100 * (d - truth["distance"]) / truth["distance"]
                        if truth["distance"]
                        else d
                        for d in distances
                    ]
                    results["results"].append(
                        {
                            "fps": fps,
                            "noise_scale": scale,
                            "speed_window_seconds": window,
                            "scenario": name,
                            "distance_error": summary(error),
                            "max_speed_mps": summary(maxima),
                            "true_max_speed_mps": truth["max_speed"],
                            "sprint_count": summary(sprints),
                            "true_sprints": truth["sprints"],
                            "active_seconds": summary(active),
                        }
                    )
    (args.output / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    for row in results["results"]:
        print(
            f"fps={row['fps']:g} noise x{row['noise_scale']:g} "
            f"window={row['speed_window_seconds']:<4g} "
            f"{row['scenario']:<28} dist_err={row['distance_error']['mean']:8.2f} "
            f"max={row['max_speed_mps']['mean']:5.2f}/{row['true_max_speed_mps']:.2f} "
            f"sprints={row['sprint_count']['mean']:.2f}/{row['true_sprints']} "
            f"active={row['active_seconds']['mean']:.2f}"
        )


if __name__ == "__main__":
    main()
