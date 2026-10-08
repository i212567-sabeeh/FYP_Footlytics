"""CLEAR MOT/Identity metrics delegated to the standard motmetrics library."""

import math
import warnings

import motmetrics as mm
import numpy as np

from app.evaluation.metrics import frame_inputs, grouped, iou_matrix, unavailable
from app.evaluation.schemas import ClipData

METRICS = [
    "idf1",
    "mota",
    "motp",
    "num_switches",
    "num_false_positives",
    "num_misses",
    "num_fragmentations",
    "mostly_tracked",
    "mostly_lost",
    "num_frames",
    "num_objects",
    "num_predictions",
    "num_unique_objects",
]
COUNTS = set(METRICS) - {"idf1", "mota", "motp"}


def accumulator(clip: ClipData, threshold: float):
    acc = mm.MOTAccumulator(auto_id=False)
    gt_frames, pred_frames = grouped(clip.annotations), grouped(clip.tracks or [])
    identities = {}
    for frame in clip.frames:
        if not frame.tracking_evaluable:
            continue
        gt, pred, _ = frame_inputs(
            gt_frames[frame.number], pred_frames[frame.number], threshold
        )
        for row in gt:
            identities.setdefault(row.track_id, len(identities) + 1)
        overlap = iou_matrix([r.box for r in gt], [r.box for r in pred])
        # motmetrics expects distance, with NaN indicating forbidden matches.
        # Construct it directly: its 1.4 IoU helper uses removed np.asfarray.
        distances = np.where(overlap >= threshold, 1 - overlap, np.nan)
        acc.update(
            [identities[r.track_id] for r in gt],
            [int(r.track_id) for r in pred],
            distances,
            frameid=frame.number,
        )
    return acc


def evaluate_tracking(
    clips: list[ClipData], threshold: float = 0.5
) -> tuple[dict, dict[str, dict]]:
    usable = [
        c
        for c in clips
        if c.tracks is not None and any(f.tracking_evaluable for f in c.frames)
    ]
    missing = {
        c.clip.clip_id: unavailable(
            "Verified tracks and identity-annotated frames are required"
        )
        for c in clips
        if c not in usable
    }
    if not usable:
        return unavailable(
            "No clips with verified tracks and genuine identity annotations"
        ), missing
    # The library produces NaN for undefined ratios (e.g. no GT); serialize null.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="invalid value encountered in", category=RuntimeWarning
        )
        summary = mm.metrics.create().compute_many(
            [accumulator(c, threshold) for c in usable],
            names=[c.clip.clip_id for c in usable],
            metrics=METRICS,
            generate_overall=True,
        )
    result = {}
    for name, row in summary.iterrows():
        values = {
            metric: (int(row[metric]) if metric in COUNTS else float(row[metric]))
            if math.isfinite(row[metric])
            else None
            for metric in METRICS
        }
        result[name] = {
            "available": True,
            **values,
            "motp_units": "mean IoU distance (1-IoU); lower is better",
        }
    overall = result.pop("OVERALL")
    return overall, result | missing
