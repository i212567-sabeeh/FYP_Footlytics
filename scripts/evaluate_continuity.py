# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Replay cached detections on a controlled clip; no YOLO, DB writes or benchmark GT.

Run from the repository root. The output directory must be new. This script can
compare stride 1 with a coarser cadence only when the input contains every frame.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["YOLO_AUTOINSTALL"] = "false"

import cv2

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.detector import is_reported
from app.cv.team_classifier import Appearance
from app.cv.team_pipeline import classify_tracking
from app.cv.tracker import ByteTrackTracker
from app.cv.tracking_pipeline import track_detections
from app.evaluation.continuity import continuity_metrics
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--team-colors",
        type=Path,
        help="Saved human-selected prototypes JSON; omitted means automatic clustering",
    )
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--strides", type=int, nargs="+", default=[5, 1])
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Use a new output directory; previous evidence is never overwritten."
        )
    summary = DetectionSummary.model_validate_json(args.summary.read_text())
    if summary.frame_stride != 1 or any(stride < 1 for stride in args.strides):
        parser.error(
            "This cadence comparison requires full-frame cached detections "
            "and positive strides."
        )
    capture = cv2.VideoCapture(str(args.video))
    fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    if (
        not math.isfinite(fps)
        or fps <= 0
        or not math.isfinite(args.seconds)
        or args.seconds <= 0
    ):
        parser.error("Invalid clip duration or video FPS.")
    frames = min(summary.decoded_frames, math.ceil(args.seconds * fps))
    duration = frames / fps
    settings = Settings(_env_file=None)
    color_data = json.loads(args.team_colors.read_text()) if args.team_colors else None
    prototypes = (
        {
            TrackTeam(p["team"]): Appearance(tuple(p["color"]), p["quality"])
            for p in color_data["prototypes"]
        }
        if color_data
        else None
    )
    args.output.mkdir(parents=True)
    save(
        args.output / "manifest.json",
        {
            "video_sha256": sha256(args.video),
            "detections_sha256": sha256(args.detections),
            "source_fps": fps,
            "decoded_frames": frames,
            "seconds": duration,
            "detector_was_run": False,
            "classification_mode": "user_seeded" if color_data else "automatic",
            "team_colors_sha256": sha256(args.team_colors)
            if args.team_colors
            else None,
            "timing_note": (
                "Only replay timings are measured. Detection timing must come "
                "from the original inference run."
            ),
            "classifier_decode": (
                "sequential OpenCV frames, without the production "
                "frame endpoint's JPEG round trip"
            ),
            "settings": {
                key: getattr(settings, key)
                for key in (
                    "track_high_thresh",
                    "track_low_thresh",
                    "track_match_thresh",
                    "track_buffer",
                    "team_unknown_threshold",
                    "team_min_samples",
                    "team_sample_interval",
                    "team_max_samples_per_track",
                    "team_min_crop_width",
                    "team_min_crop_height",
                )
            },
        },
    )
    for stride in args.strides:
        started = time.perf_counter()
        detections = args.output / f"detections-stride{stride}.csv"
        count = low = 0
        with (
            args.detections.open(newline="") as source,
            detections.open("w", newline="") as dest,
        ):
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != DETECTION_COLUMNS:
                raise ValueError("Invalid detection columns")
            writer = csv.DictWriter(dest, fieldnames=DETECTION_COLUMNS)
            writer.writeheader()
            for row in reader:
                number = int(row["frame_number"])
                if number >= frames:
                    break
                if number % stride == 0:
                    writer.writerow(row)
                    reported = is_reported(
                        float(row["confidence"]), summary.confidence_threshold
                    )
                    count += reported
                    low += not reported
        current = summary.model_copy(
            update={
                "frame_stride": stride,
                "decoded_frames": frames,
                "processed_frames": len(range(0, frames, stride)),
                "total_detections": count,
                "low_confidence_detections": low,
            }
        )
        tracker = ByteTrackTracker(
            settings,
            match_id=1,
            image_width=summary.frame_width,
            image_height=summary.frame_height,
            frame_stride=stride,
        )
        tracks = args.output / f"tracks-stride{stride}.csv"
        with tracks.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(TRACK_COLUMNS)

            def write_frame(number, stamp, rows, writer=writer):
                for row in rows:
                    writer.writerow(
                        (number, stamp, row.track_id, *row.bbox, row.confidence)
                    )

            run = track_detections(
                detections,
                current,
                tracker,
                duration=duration,
                write_frame=write_frame,
                progress=lambda *_: None,
            )
        timing = time.perf_counter() - started
        metrics = continuity_metrics(
            tracks, frame_stride=stride, duration_seconds=duration
        )
        metrics.update(
            {
                "tracking_seconds": timing,
                "effective_update_fps": fps / stride,
                "lost_track_buffer_seconds": tracker.track_buffer_updates
                * stride
                / fps,
            }
        )
        save(args.output / f"continuity-stride{stride}.json", metrics)
        tracking = TrackingSummary(
            **asdict(run),
            frame_stride=stride,
            frame_width=summary.frame_width,
            frame_height=summary.frame_height,
            detection_job_id=1,
            detection_attempt=0,
            track_high_thresh=settings.track_high_thresh,
            track_low_thresh=settings.track_low_thresh,
            track_match_thresh=settings.track_match_thresh,
            track_buffer=settings.track_buffer,
        )
        capture = cv2.VideoCapture(str(args.video))
        next_number = 0

        def load_frame(number, capture=capture):
            nonlocal next_number
            if number < next_number:
                raise ValueError("Classification requested unordered frames")
            while next_number <= number:
                if not capture.grab():
                    raise ValueError("Video ended before the selected frame")
                next_number += 1
            ok, image = capture.retrieve()
            if not ok:
                raise ValueError("Selected frame could not be decoded")
            return image

        try:
            start = time.perf_counter()
            classified = classify_tracking(
                tracks,
                current,
                tracking,
                duration,
                settings,
                load_frame=load_frame,
                progress=lambda *_: None,
                prototypes=prototypes,
            )
            classified_seconds = time.perf_counter() - start
        finally:
            capture.release()
        save(
            args.output / f"classification-stride{stride}.json",
            {
                "diagnostics": classified.diagnostics,
                "valid_samples": classified.valid_samples,
                "sampled_frames": classified.sampled_frames,
                "counts": dict(Counter(str(p.team) for p in classified.predictions)),
                "processing_seconds": classified_seconds,
                "predictions": [asdict(p) for p in classified.predictions],
            },
        )
        print(
            json.dumps(
                {
                    "stride": stride,
                    "continuity": metrics,
                    "teams": dict(Counter(str(p.team) for p in classified.predictions)),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
