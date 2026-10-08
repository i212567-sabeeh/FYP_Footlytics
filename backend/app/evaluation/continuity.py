"""Read-only continuity statistics for a controlled, cached tracking artifact.

This is independent of the frozen Phase 15 metrics. New IDs/minute is only a
fragmentation proxy: without identity ground truth it cannot establish IDF1.
"""

import csv
import math
from collections import defaultdict
from pathlib import Path

import numpy as np


def continuity_metrics(
    path: Path, *, frame_stride: int, duration_seconds: float
) -> dict:
    if frame_stride < 1 or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("A positive stride and measured clip duration are required")
    tracks: dict[int, list[tuple[int, float]]] = defaultdict(list)
    previous_frame = -1
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            frame, stamp, track_id = (
                int(row["frame_number"]),
                float(row["timestamp_seconds"]),
                int(row["track_id"]),
            )
            if (
                frame < previous_frame
                or frame < 0
                or frame % frame_stride
                or track_id < 1
                or not math.isfinite(stamp)
                or stamp < 0
            ):
                raise ValueError("Invalid ordered tracking metadata")
            previous_frame = frame
            if stamp >= duration_seconds:
                continue
            values = tracks[track_id]
            if values and (frame <= values[-1][0] or stamp <= values[-1][1]):
                raise ValueError("Duplicate or non-increasing track observation")
            values.append((frame, stamp))
    spans = np.asarray([values[-1][1] - values[0][1] for values in tracks.values()])
    observed = [
        sum(
            b[1] - a[1]
            for a, b in zip(values, values[1:], strict=False)
            if b[0] - a[0] == frame_stride
        )
        for values in tracks.values()
    ]
    return {
        "unique_tracks": len(tracks),
        "tracks_with_multiple_observations": sum(len(v) >= 2 for v in tracks.values()),
        "tracks_with_consecutive_observations": sum(v > 0 for v in observed),
        "mean_duration_seconds": float(spans.mean()) if len(spans) else None,
        "median_duration_seconds": float(np.median(spans)) if len(spans) else None,
        "p90_duration_seconds": float(np.percentile(spans, 90)) if len(spans) else None,
        "p95_duration_seconds": float(np.percentile(spans, 95)) if len(spans) else None,
        "longest_duration_seconds": float(spans.max()) if len(spans) else None,
        "tracks_at_least_10_seconds": int(sum(spans >= 10)),
        "tracks_at_least_30_seconds": int(sum(spans >= 30)),
        "very_short_tracks_under_2_seconds": int(sum(spans < 2)),
        "new_ids_per_video_minute_proxy": len(tracks) * 60 / duration_seconds,
        "total_consecutively_observed_track_seconds": sum(observed),
        "definitions": (
            "Duration is last minus first timestamp (span), not continuous occupancy. "
            "Usable tracks have at least one consecutive sampled interval. "
            "New IDs/minute is a proxy, not IDF1 or proof of identity continuity."
        ),
    }
