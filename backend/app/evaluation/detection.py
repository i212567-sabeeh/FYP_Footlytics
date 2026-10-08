"""Fixed-operating-point counts and confidence-ranked, all-points AP50."""

import numpy as np

from app.evaluation.metrics import (
    assign,
    frame_inputs,
    grouped,
    iou_matrix,
    ratio,
    unavailable,
)
from app.evaluation.schemas import ClipData


def average_precision(clips: list[ClipData], threshold: float = 0.5) -> float | None:
    frames, predictions, count = {}, [], 0
    for clip in clips:
        gt_by_frame, pred_by_frame = (
            grouped(clip.annotations),
            grouped(clip.detections or []),
        )
        for frame in clip.frames:
            rows = gt_by_frame[frame.number]
            gt = [r for r in rows if not r.ignored and r.team != "official"]
            ignored = [r for r in rows if r.ignored or r.team == "official"]
            pred = pred_by_frame[frame.number]
            key = (clip.clip.clip_id, frame.number)
            frames[key] = (gt, ignored, set())
            count += len(gt)
            for index, row in enumerate(pred):
                predictions.append((row.confidence, key, index, row))
    if count == 0:
        return None
    # Stable, deterministic ties; scores never influence GT selection/annotation.
    predictions.sort(key=lambda item: (-item[0], item[1], item[2]))
    hits = []
    for _, key, _, row in predictions:
        gt, ignored, used = frames[key]
        overlaps = iou_matrix([row.box], [g.box for g in gt])[0]
        best = int(overlaps.argmax()) if len(overlaps) else None
        eligible_match = best is not None and overlaps[best] >= threshold
        # AP matching follows confidence order, independently of count matching.
        # A duplicate scored-player hit remains FP even near an ignored region.
        if (
            not eligible_match
            and ignored
            and np.any(iou_matrix([row.box], [g.box for g in ignored]) >= threshold)
        ):
            continue
        hit = eligible_match and best not in used
        hits.append(int(hit))
        if hit:
            used.add(best)
    if not hits:
        return 0.0
    true_positives = np.cumsum(hits)
    precision = true_positives / np.arange(1, len(hits) + 1)
    recall = true_positives / count
    # VOC-style all-points interpolated precision envelope, not COCO mAP.
    precision = np.maximum.accumulate(np.r_[precision, 0][::-1])[::-1]
    return float(np.sum(np.diff(np.r_[0, recall]) * precision[:-1]))


def evaluate_detection(clips: list[ClipData], threshold: float = 0.5) -> dict:
    usable = [clip for clip in clips if clip.detections is not None]
    if not usable:
        return unavailable("No verified detection artifacts with reviewed frames")
    frames = gt_count = predicted = ignored = tp = 0
    overlaps = []
    for clip in usable:
        gt_by_frame, pred_by_frame = grouped(clip.annotations), grouped(clip.detections)
        for frame in clip.frames:
            frames += 1
            raw = pred_by_frame[frame.number]
            gt, pred, suppressed = frame_inputs(
                gt_by_frame[frame.number], raw, threshold
            )
            matches = assign(
                iou_matrix([g.box for g in gt], [p.box for p in pred]), threshold
            )
            tp += len(matches)
            overlaps.extend(iou for _, _, iou in matches)
            gt_count += len(gt)
            predicted += len(raw)
            ignored += suppressed
    fp, fn = predicted - ignored - tp, gt_count - tp
    return {
        "available": True,
        "clips": len(usable),
        "annotated_frames": frames,
        "ground_truth_boxes": gt_count,
        "predicted_boxes": predicted,
        "ignored_predictions": ignored,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "mean_matched_iou": float(np.mean(overlaps)) if overlaps else None,
        "ap50": average_precision(usable),
        "ap50_protocol": (
            "All-points interpolated AP at IoU 0.50 over saved "
            "confidence-filtered predictions; not COCO mAP"
        ),
    }
