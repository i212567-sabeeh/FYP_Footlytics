"""Shared overlap and assignment rules, independent of model predictions."""

from collections import defaultdict
from collections.abc import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from app.evaluation.schemas import Observation


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def iou_matrix(first: Sequence, second: Sequence) -> np.ndarray:
    a = np.asarray(first, dtype=float).reshape(-1, 4)
    b = np.asarray(second, dtype=float).reshape(-1, 4)
    for boxes in (a, b):
        if not np.isfinite(boxes).all() or np.any(boxes[:, 2:] <= boxes[:, :2]):
            raise ValueError("IoU requires finite, positive-area boxes")
    low = np.maximum(a[:, None, :2], b[None, :, :2])
    high = np.minimum(a[:, None, 2:], b[None, :, 2:])
    intersection = np.maximum(high - low, 0).prod(axis=2)
    area_a = (a[:, 2:] - a[:, :2]).prod(axis=1)
    area_b = (b[:, 2:] - b[:, :2]).prod(axis=1)
    return intersection / (area_a[:, None] + area_b[None, :] - intersection)


def assign(overlap: np.ndarray, threshold: float) -> list[tuple[int, int, float]]:
    """Maximize valid match count, then total IoU; invalid edges never match.

    Maximizing raw IoU before thresholding can discard two valid matches in
    favor of one excellent and one invalid edge. A cardinality bonus avoids it.
    """
    if not 0 < threshold <= 1 or not np.isfinite(overlap).all():
        raise ValueError("Invalid matching threshold or overlap matrix")
    if not overlap.size:
        return []
    valid = overlap >= threshold
    weights = np.where(valid, min(overlap.shape) + 1 + overlap, 0)
    rows, columns = linear_sum_assignment(weights, maximize=True)
    return [
        (int(a), int(b), float(overlap[a, b]))
        for a, b in zip(rows, columns, strict=True)
        if valid[a, b]
    ]


def grouped(rows: list[Observation]) -> dict[int, list[Observation]]:
    result = defaultdict(list)
    for row in rows:
        result[row.frame].append(row)
    return result


def frame_inputs(
    gt: list[Observation], predictions: list[Observation], threshold: float
) -> tuple[list[Observation], list[Observation], int]:
    """Match scored players first, then suppress unmatched ignored-region hits.

    Officials are explicitly ignored for this player-only evaluation. This is
    a documented local ignore policy, not a claim of full MOTChallenge protocol.
    """
    players = [row for row in gt if not row.ignored and row.team != "official"]
    ignored = [row for row in gt if row.ignored or row.team == "official"]
    if not ignored or not predictions:
        return players, predictions, 0
    matches = assign(
        iou_matrix([r.box for r in players], [r.box for r in predictions]), threshold
    )
    matched = {b for _, b, _ in matches}
    overlap = iou_matrix([r.box for r in ignored], [r.box for r in predictions])
    keep = [
        index
        for index in range(len(predictions))
        if index in matched or not np.any(overlap[:, index] >= threshold)
    ]
    return players, [predictions[index] for index in keep], len(predictions) - len(keep)


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}
