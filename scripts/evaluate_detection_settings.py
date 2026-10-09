# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Compare YOLO inference sizes on SoccerNet-GSR with the production detector.

An explicit experiment, separate from the frozen Phase 15 predictor (which
refuses changed settings): only YOLO_IMAGE_SIZE varies. Each size runs the
unchanged detector, detect_video and ByteTrack on the same frames and CPU, then
the unchanged evaluators score reported detections (confidence >= YOLO_CONFIDENCE)
and tracks. Run from the repository root; the output directory must be new.
"""

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["YOLO_AUTOINSTALL"] = "false"

from app.core.config import Settings
from app.cv.detector import YoloPlayerDetector
from app.cv.pipeline import detect_video
from app.cv.tracker import ByteTrackTracker
from app.cv.tracking_pipeline import track_detections
from app.evaluation.detection import evaluate_detection
from app.evaluation.inputs import load_dataset
from app.evaluation.schemas import EvaluationConfig, Observation
from app.evaluation.tracking import evaluate_tracking
from app.schemas.detection import DetectionSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS


def run_size(size: int, clips, dataset_path: Path, out: Path) -> dict:
    settings = Settings(_env_file=None, yolo_image_size=size)
    detector = YoloPlayerDetector(settings)
    timing = {}
    for clip in clips:
        meta = clip.clip
        folder = out / meta.clip_id
        folder.mkdir(parents=True)
        path = folder / "detections.csv"
        observations, calls = [], []
        with path.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(DETECTION_COLUMNS)

            def write(
                frame, detections, writer=writer, observations=observations, meta=meta
            ):
                for item in detections:
                    writer.writerow(
                        (
                            frame.number,
                            frame.timestamp_seconds,
                            *item.bbox,
                            item.confidence,
                            item.class_id,
                            item.class_name,
                            meta.width,
                            meta.height,
                        )
                    )
                    observations.append(
                        Observation(
                            frame.number,
                            frame.timestamp_seconds,
                            item.bbox,
                            confidence=item.confidence,
                        )
                    )

            class Timed:
                def detect(self, image, calls=calls):
                    start = time.perf_counter()
                    result = detector.detect(image)
                    calls.append(time.perf_counter() - start)
                    return result

            start = time.perf_counter()
            run = detect_video(
                (dataset_path.parent / meta.video.path).resolve(),
                Timed(),
                stride=1,
                image_width=meta.width,
                image_height=meta.height,
                roi=None,
                confidence_threshold=settings.yolo_confidence,
                write_frame=write,
                progress=lambda *_: None,
            )
            wall = time.perf_counter() - start
        clip.detections = observations
        summary = DetectionSummary(
            **asdict(run),
            average_detections_per_processed_frame=run.total_detections
            / run.processed_frames,
            frame_stride=1,
            frame_width=meta.width,
            frame_height=meta.height,
            model=detector.model_name,
            device=detector.device,
            confidence_threshold=settings.yolo_confidence,
            candidate_confidence_threshold=settings.detection_candidate_confidence,
            inference_image_size=size,
            roi_filter_applied=False,
            roi_skip_reason="Offline experiment",
            calibration_id=0,
            calibration_updated_at=datetime.now(UTC),
        )
        tracks = []
        tracker = ByteTrackTracker(
            settings,
            match_id=int(meta.clip_id.split("-")[-1]),
            image_width=meta.width,
            image_height=meta.height,
        )

        def write_tracks(number, timestamp, rows, tracks=tracks):
            for row in rows:
                tracks.append(
                    Observation(
                        number,
                        timestamp,
                        tuple(row.bbox),
                        str(row.track_id),
                        confidence=row.confidence,
                    )
                )

        track_detections(
            path,
            summary,
            tracker,
            duration=meta.duration_seconds,
            write_frame=write_tracks,
            progress=lambda *_: None,
        )
        clip.tracks = tracks
        timing[meta.clip_id] = {
            "detect_video_seconds": wall,
            "frames": run.processed_frames,
            "effective_fps": run.processed_frames / wall,
            "mean_inference_seconds_after_first": sum(calls[1:])
            / max(1, len(calls) - 1),
            "reported_detections": run.total_detections,
            "low_confidence_candidates": run.low_confidence_detections,
        }
    config = EvaluationConfig()
    tracking, _ = evaluate_tracking(clips, config.tracking_iou)
    return {
        "yolo_image_size": size,
        "timing": timing,
        "detection": evaluate_detection(
            clips, config.detection_iou, settings.yolo_confidence
        ),
        "tracking": tracking,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--image-sizes", type=int, nargs="+", default=[640, 960, 1280])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    _, clips, _, _ = load_dataset(args.dataset, None, EvaluationConfig())
    results = []
    for size in args.image_sizes:
        result = run_size(size, clips, args.dataset, args.output / str(size))
        results.append(result)
        d, t = result["detection"], result["tracking"]
        frames = sum(item["frames"] for item in result["timing"].values())
        seconds = sum(
            item["detect_video_seconds"] for item in result["timing"].values()
        )
        print(
            f"imgsz={size} P={d['precision']:.4f} R={d['recall']:.4f} "
            f"F1={d['f1']:.4f} AP50={d['ap50']:.4f} IDF1={t['idf1']:.4f} "
            f"MOTA={t['mota']:.4f} IDSW={t['num_switches']} "
            f"fps={frames / seconds:.2f}",
            flush=True,
        )
        (args.output / "results.json").write_text(
            json.dumps(results, indent=2, default=str), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
