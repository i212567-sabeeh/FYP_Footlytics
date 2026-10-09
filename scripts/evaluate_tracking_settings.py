# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Score ByteTrack settings on SoccerNet-GSR from cached detections; no YOLO.

Replays the production ByteTrackTracker and track_detections over saved
detection CSVs (including ByteTrack's low-score candidates) and scores the
tracks with the unchanged motmetrics-based evaluator. Variants change only
declared track_* settings (--set NAME=VALUE). Run from the repository root;
the output directory must be new.
"""

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings
from app.cv.detector import is_reported
from app.cv.tracker import ByteTrackTracker
from app.cv.tracking_pipeline import track_detections
from app.evaluation.inputs import load_dataset
from app.evaluation.schemas import EvaluationConfig, Observation
from app.evaluation.tracking import evaluate_tracking
from app.schemas.detection import DetectionSummary


def parse_override(text: str) -> tuple[str, object]:
    name, _, value = text.partition("=")
    if name not in Settings.model_fields or not name.startswith("track_"):
        raise SystemExit(f"Only track_* settings can be overridden, not {name!r}")
    return name, json.loads(value)


def detection_summary(clip, path: Path, settings: Settings) -> DetectionSummary:
    with path.open(newline="", encoding="utf-8") as stream:
        scores = [float(row["confidence"]) for row in csv.DictReader(stream)]
    reported = sum(is_reported(score, settings.yolo_confidence) for score in scores)
    return DetectionSummary(
        processed_frames=clip.frame_count,
        decoded_frames=clip.frame_count,
        total_detections=reported,
        low_confidence_detections=len(scores) - reported,
        average_detections_per_processed_frame=reported / clip.frame_count,
        frame_stride=1,
        frame_width=clip.width,
        frame_height=clip.height,
        timestamp_fallback_frames=0,
        model="cached",
        device="cpu",
        confidence_threshold=settings.yolo_confidence,
        candidate_confidence_threshold=settings.detection_candidate_confidence,
        inference_image_size=settings.yolo_image_size,
        roi_filter_applied=False,
        roi_skip_reason="Offline replay of cached detections",
        calibration_id=0,
        calibration_updated_at=datetime.now(UTC),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path, help="Verified prediction manifest")
    source.add_argument(
        "--detections-root",
        type=Path,
        help="Folder of <clip>/detections.csv (evaluate_detection_settings.py output)",
    )
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    overrides = dict(parse_override(item) for item in args.overrides)
    settings = Settings(_env_file=None, **overrides)
    _, clips, _, _ = load_dataset(args.dataset, args.predictions, EvaluationConfig())
    root = args.predictions.parent if args.predictions else args.detections_root
    result = {"overrides": overrides, "clips": {}}
    for clip in clips:
        clip_id = clip.clip.clip_id
        path = root / clip_id / "detections.csv"
        tracker = ByteTrackTracker(
            settings,
            match_id=int(clip_id.split("-")[-1]),
            image_width=clip.clip.width,
            image_height=clip.clip.height,
        )
        rows = []

        def write(number, timestamp, tracks, rows=rows):
            for track in tracks:
                rows.append(
                    Observation(
                        number,
                        timestamp,
                        tuple(track.bbox),
                        str(track.track_id),
                        confidence=track.confidence,
                    )
                )

        start = time.perf_counter()
        run = track_detections(
            path,
            detection_summary(clip.clip, path, settings),
            tracker,
            duration=clip.clip.duration_seconds,
            write_frame=write,
            progress=lambda *_: None,
        )
        clip.tracks = rows
        result["clips"][clip_id] = {
            "seconds": time.perf_counter() - start,
            "unique_tracks": run.unique_tracks,
            "track_rows": len(rows),
        }
    overall, per_clip = evaluate_tracking(clips, EvaluationConfig().tracking_iou)
    result["overall"] = overall
    for clip_id, metrics in per_clip.items():
        result["clips"][clip_id]["metrics"] = metrics
    (args.output / "results.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    keys = ("idf1", "mota", "num_switches", "num_fragmentations")
    keys += ("num_false_positives", "num_misses")
    print(json.dumps({"overrides": overrides, **{k: overall.get(k) for k in keys}}))


if __name__ == "__main__":
    main()
