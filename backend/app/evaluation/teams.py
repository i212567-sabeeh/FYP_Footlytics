"""Automatic classification, aligned by spatial evidence rather than team labels."""

from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.evaluation.metrics import assign, grouped, iou_matrix, ratio, unavailable
from app.evaluation.schemas import ClipData

CLASSES = ("team_a", "team_b")
PREDICTED = (*CLASSES, "unknown")


def spatial_identity_mapping(clip: ClipData, threshold: float) -> dict[str, str]:
    counts = Counter()
    gt_frames, pred_frames = grouped(clip.annotations), grouped(clip.tracks or [])
    for frame in clip.frames:
        gt = [
            r
            for r in gt_frames[frame.number]
            if r.track_id and not r.ignored and r.team != "official"
        ]
        pred = pred_frames[frame.number]
        for a, b, _ in assign(
            iou_matrix([r.box for r in gt], [r.box for r in pred]), threshold
        ):
            counts[(gt[a].track_id, pred[b].track_id)] += 1
    gt_ids = sorted({key[0] for key in counts})
    pred_ids = sorted({key[1] for key in counts})
    if not gt_ids or not pred_ids:
        return {}
    weights = np.array([[counts[(g, p)] for p in pred_ids] for g in gt_ids])
    rows, columns = linear_sum_assignment(weights, maximize=True)
    return {
        gt_ids[a]: pred_ids[b]
        for a, b in zip(rows, columns, strict=True)
        if weights[a, b] > 0
    }


def summarize(matrix: dict[str, dict[str, int]], associated: int) -> dict:
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[team][team] for team in CLASSES)
    unknown = sum(row["unknown"] for row in matrix.values())
    per_class = {}
    for team in CLASSES:
        tp = matrix[team][team]
        fp = sum(matrix[other][team] for other in CLASSES if other != team)
        fn = sum(matrix[team].values()) - tp
        per_class[team] = {
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn),
            "support": tp + fn,
        }
    return {
        "available": True,
        "eligible_tracks": total,
        "associated_tracks": associated,
        "accuracy": ratio(correct, total),
        "accuracy_among_classified": ratio(correct, total - unknown),
        "unknown_predictions": unknown,
        "unknown_rate": ratio(unknown, total),
        "classified_tracks": total - unknown,
        "coverage": ratio(total - unknown, total),
        "confusion_matrix": matrix,
        "per_class": per_class,
    }


def evaluate_teams(clips: list[ClipData], threshold: float = 0.5) -> dict:
    matrix = {a: dict.fromkeys(PREDICTED, 0) for a in CLASSES}
    associated = eligible = 0
    for clip in clips:
        if (
            clip.automatic_teams is None
            or clip.tracks is None
            or clip.clip.team_mapping is None
        ):
            continue
        labels = {
            r.track_id: r.team
            for r in clip.annotations
            if r.track_id and not r.ignored and r.team in CLASSES
        }
        mapping = spatial_identity_mapping(clip, threshold)
        for identity, gt_team in labels.items():
            eligible += 1
            pred_id = mapping.get(identity)
            associated += int(pred_id is not None)
            predicted = clip.automatic_teams.get(pred_id, "unknown")
            predicted = clip.clip.team_mapping.get(predicted, "unknown")
            matrix[gt_team][predicted] += 1
    if not eligible:
        return unavailable(
            "Team-labelled GT tracks, automatic labels and an explicit "
            "clip color mapping are required"
        )
    return summarize(matrix, associated)
