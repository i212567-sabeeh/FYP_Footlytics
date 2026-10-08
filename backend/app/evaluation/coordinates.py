"""Physical errors require held-out landmarks or independent player positions."""

import math

import numpy as np

from app.cv.homography import compute_homography, transform_points
from app.evaluation.metrics import assign, grouped, iou_matrix
from app.evaluation.schemas import ClipData


def error_summary(errors: list[float], minimum_p95: int = 20) -> dict:
    if any(not math.isfinite(value) or value < 0 for value in errors):
        raise ValueError("Position errors must be finite and non-negative")
    return {
        "available": bool(errors),
        "observations": len(errors),
        "units": "metres",
        "mean": float(np.mean(errors)) if errors else None,
        "median": float(np.median(errors)) if errors else None,
        "rmse": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
        "max": max(errors) if errors else None,
        "p95": float(np.percentile(errors, 95)) if len(errors) >= minimum_p95 else None,
        "p95_reason": None
        if len(errors) >= minimum_p95
        else f"At least {minimum_p95} observations required",
        "reason": None if errors else "No independently validated paired positions",
    }


def landmark_errors(clip: ClipData) -> list[float]:
    fit = [p for p in clip.landmarks if p.role == "fit"]
    validation = [p for p in clip.landmarks if p.role == "validation"]
    if not validation or len(fit) < 4:
        return []
    matrix = compute_homography([p.image for p in fit], [p.pitch for p in fit])
    projected = transform_points([p.image for p in validation], matrix)
    return [
        math.dist(point, truth.pitch)
        for point, truth in zip(projected, validation, strict=True)
    ]


def player_errors(clip: ClipData, threshold: float) -> tuple[list[float], int]:
    errors, eligible = [], 0
    gt_frames, pred_frames = grouped(clip.annotations), grouped(clip.coordinates or [])
    for frame in clip.frames:
        gt = [
            r
            for r in gt_frames[frame.number]
            if r.pitch is not None and not r.ignored and r.team != "official"
        ]
        eligible += len(gt)
        pred = pred_frames[frame.number]
        for a, b, _ in assign(
            iou_matrix([r.box for r in gt], [r.box for r in pred]), threshold
        ):
            errors.append(math.dist(gt[a].pitch, pred[b].pitch))
    return errors, eligible


def evaluate_coordinates(
    clips: list[ClipData], threshold: float = 0.5, minimum_p95: int = 20
) -> dict:
    landmarks, players, eligible = [], [], 0
    for clip in clips:
        landmarks.extend(landmark_errors(clip))
        errors, count = player_errors(clip, threshold)
        players.extend(errors)
        eligible += count
    return {
        "calibration": error_summary(landmarks, minimum_p95),
        "player_coordinates": error_summary(players, minimum_p95)
        | {
            "ground_truth_positions": eligible,
            "unmatched_ground_truth_positions": eligible - len(players),
        },
    }
