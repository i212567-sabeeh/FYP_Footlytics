"""Bounded offline real predictions using the unchanged production CV modules.

Consumes an already validated/frozen canonical subset; never scans Match storage.
Completed per-clip artifacts can be reused only with matching provenance/hashes.
"""

import argparse
import csv
import json
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import cv2

from app.core.config import PROJECT_ROOT, Settings
from app.cv.detector import BaseDetector, YoloPlayerDetector
from app.cv.pipeline import detect_video
from app.cv.team_pipeline import classify_tracking
from app.cv.tracker import ByteTrackTracker
from app.cv.tracking_pipeline import track_detections
from app.evaluation.configuration import digest_json, pipeline_snapshot
from app.evaluation.inputs import checked_file, load_dataset, sha256
from app.evaluation.runtime import environment
from app.evaluation.schemas import (
    EvaluationConfig,
    FileRef,
    InputError,
    PredictionClip,
    Predictions,
    RuntimeMeasurement,
)
from app.schemas.detection import DetectionSummary
from app.schemas.tracking import TrackingSummary
from app.services.detection_artifacts import COLUMNS as DETECTION_COLUMNS
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS


def source_digest() -> str:
    paths = [
        *sorted((PROJECT_ROOT / "backend/app/cv").glob("*.py")),
        PROJECT_ROOT / "backend/app/core/config.py",
        Path(__file__),
    ]
    return digest_json(
        {p.relative_to(PROJECT_ROOT).as_posix(): sha256(p) for p in paths}
    )


class TimedDetector(BaseDetector):
    def __init__(self, detector: BaseDetector):
        self.detector = detector
        self.calls: list[float] = []

    def detect(self, frame):
        start = perf_counter()
        result = self.detector.detect(frame)
        self.calls.append(perf_counter() - start)
        return result


def predict_clip(
    clip,
    video: Path,
    out: Path,
    settings: Settings,
    detector: YoloPlayerDetector,
    machine: dict,
    config_hash: str,
) -> tuple[PredictionClip, dict]:
    runtime = []
    hardware = str(machine.get("cpu", "CPU"))

    def measured(stage, start, method, setup=False):
        runtime.append(
            RuntimeMeasurement(
                stage=stage,
                seconds=perf_counter() - start,
                frames=clip.frame_count,
                device="cpu",
                setup_included=setup,
                hardware=hardware,
                measurement_method=method,
            )
        )

    def progress(done, total):
        if done % 50 == 0:
            print(f"{clip.clip_id}: processed {done}/{total} frames", flush=True)

    timed = TimedDetector(detector)
    start = perf_counter()
    detections_path = out / "detections.csv"
    with detections_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(DETECTION_COLUMNS)

        def write_detection(frame, detections):
            for detection in detections:
                writer.writerow(
                    (
                        frame.number,
                        frame.timestamp_seconds,
                        *detection.bbox,
                        detection.confidence,
                        detection.class_id,
                        detection.class_name,
                        clip.width,
                        clip.height,
                    )
                )

        detection_run = detect_video(
            video,
            timed,
            stride=settings.detection_frame_stride,
            image_width=clip.width,
            image_height=clip.height,
            roi=None,
            confidence_threshold=settings.yolo_confidence,
            write_frame=write_detection,
            progress=progress,
        )
    measured(
        "detection",
        start,
        (
            "perf_counter around unchanged detect_video; includes PNG MOV "
            "decode, CSV writes and first-predict lazy setup; model "
            "construction recorded separately"
        ),
        setup=True,
    )
    if detection_run.processed_frames != clip.frame_count:
        raise InputError("Processed frame count differs from the frozen interval")
    # Offline-only sentinel IDs: no Match/Video/Calibration/Job database records
    # are created or claimed. These unused legacy summary fields never reach GT.
    detection_summary = DetectionSummary(
        **asdict(detection_run),
        average_detections_per_processed_frame=detection_run.total_detections
        / clip.frame_count,
        frame_stride=settings.detection_frame_stride,
        frame_width=clip.width,
        frame_height=clip.height,
        model=detector.model_name,
        device=detector.device,
        confidence_threshold=settings.yolo_confidence,
        candidate_confidence_threshold=settings.detection_candidate_confidence,
        inference_image_size=settings.yolo_image_size,
        roi_filter_applied=False,
        roi_skip_reason=(
            "No four verified pitch-corner correspondences in this offline subset"
        ),
        calibration_id=0,
        calibration_updated_at=datetime.now(UTC),
    )
    tracks_path = out / "tracks.csv"
    start = perf_counter()
    tracker = ByteTrackTracker(
        settings,
        match_id=int(clip.clip_id.split("-")[-1]),
        image_width=clip.width,
        image_height=clip.height,
        frame_stride=settings.detection_frame_stride,
    )
    with tracks_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(TRACK_COLUMNS)

        def write_track(number, timestamp, tracks):
            for track in tracks:
                writer.writerow(
                    (number, timestamp, track.track_id, *track.bbox, track.confidence)
                )

        tracking_run = track_detections(
            detections_path,
            detection_summary,
            tracker,
            duration=clip.duration_seconds,
            write_frame=write_track,
            progress=progress,
        )
    measured(
        "tracking",
        start,
        (
            "perf_counter; ByteTrack initialization, production detection CSV "
            "streaming, all consecutive frame updates and CSV writes"
        ),
        setup=True,
    )
    tracking_summary = TrackingSummary(
        **asdict(tracking_run),
        frame_stride=settings.detection_frame_stride,
        frame_width=clip.width,
        frame_height=clip.height,
        detection_job_id=0,
        detection_attempt=0,
        track_high_thresh=settings.track_high_thresh,
        track_low_thresh=settings.track_low_thresh,
        track_match_thresh=settings.track_match_thresh,
        track_buffer=settings.track_buffer,
    )
    start = perf_counter()
    capture = cv2.VideoCapture(str(video))

    def load_frame(number):
        capture.set(cv2.CAP_PROP_POS_FRAMES, number)
        ok, frame = capture.read()
        if not ok:
            raise InputError("Could not decode a sampled jersey frame")
        return frame

    try:
        classification = classify_tracking(
            tracks_path,
            detection_summary,
            tracking_summary,
            clip.duration_seconds,
            settings,
            load_frame=load_frame,
            progress=progress,
        )
    finally:
        capture.release()
    teams_path = out / "teams.csv"
    with teams_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("track_id", "automatic_team", "automatic_confidence"))
        writer.writerows(
            (p.track_id, p.team.value, p.confidence) for p in classification.predictions
        )
    measured(
        "team_classification",
        start,
        (
            "perf_counter; production classify_tracking, bounded frame decode,"
            " jersey feature extraction, clustering and automatic CSV writes"
        ),
    )
    refs = {
        name: FileRef(path=f"{clip.clip_id}/{path.name}", sha256=sha256(path))
        for name, path in (
            ("detections", detections_path),
            ("tracks", tracks_path),
            ("automatic_teams", teams_path),
        )
    }
    prediction = PredictionClip(
        clip_id=clip.clip_id,
        video_sha256=clip.video.sha256,
        pipeline_config_sha256=config_hash,
        processed_frames=list(range(clip.frame_count)),
        runtime=runtime,
        **refs,
    )
    diagnostics = {
        "detection": asdict(detection_run),
        "tracking": asdict(tracking_run),
        "team_sampled_frames": classification.sampled_frames,
        "team_valid_samples": classification.valid_samples,
        "yolo_call_seconds": sum(timed.calls),
        "first_yolo_call_seconds": timed.calls[0],
        "remaining_yolo_calls_seconds": sum(timed.calls[1:]),
        "remaining_yolo_calls": len(timed.calls) - 1,
        "roi_applied": False,
        "roi_skip_reason": detection_summary.roi_skip_reason,
        "offline_only": True,
    }
    return prediction, diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--clip",
        help="One preselected clip for the initial smoke; others remain pending",
    )
    args = parser.parse_args()
    dataset, _, _, _ = load_dataset(
        args.dataset, None, EvaluationConfig(), allow_synthetic=False
    )
    if not 1 <= len(dataset.clips) <= 3 or any(
        c.frame_count != 150 for c in dataset.clips
    ):
        raise InputError(
            "This real run is bounded to three preselected 150-frame clips"
        )
    frozen = json.loads((args.dataset.parent / "provenance.json").read_text())
    settings = Settings()
    config = pipeline_snapshot(settings)
    if config != frozen["pipeline_config"]:
        raise InputError("Settings changed since the independent pre-inference freeze")
    if args.clip and args.clip not in {c.clip_id for c in dataset.clips}:
        raise InputError("Requested clip was not selected before inference")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    weights = Path(settings.yolo_model)
    weights = (
        settings.storage_dir / "models" / weights
        if weights.parent == Path(".")
        else PROJECT_ROOT / weights
    )
    if not weights.is_file():
        raise InputError(
            "Expected existing YOLO weights; this evaluation never downloads a model"
        )
    machine = environment(probe_torch=True)
    revision = source_digest()
    key = {
        "dataset_sha256": sha256(args.dataset),
        "weights_sha256": sha256(weights),
        "pipeline_config_sha256": digest_json(config),
        "source_sha256": revision,
        "processed_frames": list(range(150)),
    }
    detector = None
    model_load_seconds = None
    for clip in dataset.clips:
        if args.clip and clip.clip_id != args.clip:
            continue
        destination = out / clip.clip_id
        if destination.exists():
            cached = json.loads((destination / "prediction.json").read_text())
            if (
                cached["reuse_key"] != key
                or cached["prediction"]["video_sha256"] != clip.video.sha256
            ):
                raise InputError(
                    "Existing prediction provenance differs; no automatic overwrite"
                )
            prediction = PredictionClip.model_validate(cached["prediction"])
            for ref in (
                prediction.detections,
                prediction.tracks,
                prediction.automatic_teams,
            ):
                checked_file(out, ref)
            print(
                f"Reused verified prediction artifacts for {clip.clip_id}", flush=True
            )
            continue
        model_load_seconds = None
        started_at = datetime.now(UTC).isoformat()
        if detector is None:
            start = perf_counter()
            detector = YoloPlayerDetector(settings)
            model_load_seconds = perf_counter() - start
            if detector.device != "cpu":
                raise InputError("This frozen runtime report expects CPU inference")
        video = checked_file(args.dataset.parent, clip.video)
        with tempfile.TemporaryDirectory(
            prefix=f".{clip.clip_id}-", dir=out
        ) as temporary:
            attempt = Path(temporary)
            prediction, diagnostics = predict_clip(
                clip,
                video,
                attempt,
                settings,
                detector,
                machine,
                key["pipeline_config_sha256"],
            )
            checked_file(args.dataset.parent, clip.video)
            if (
                sha256(args.dataset) != key["dataset_sha256"]
                or sha256(weights) != key["weights_sha256"]
                or source_digest() != revision
            ):
                raise InputError("Inputs or source code changed during prediction")
            cached = {
                "started_at": started_at,
                "completed_at": datetime.now(UTC).isoformat(),
                "reuse_key": key,
                "prediction": prediction.model_dump(mode="json"),
                "diagnostics": diagnostics,
                "model_load_seconds_this_process": model_load_seconds,
                "environment": machine,
            }
            (attempt / "prediction.json").write_text(
                json.dumps(cached, indent=2, allow_nan=False), encoding="utf-8"
            )
            attempt.rename(destination)
        print(f"Published completed real predictions for {clip.clip_id}", flush=True)
    completed = []
    for clip in dataset.clips:
        path = out / clip.clip_id / "prediction.json"
        if path.exists():
            cached = json.loads(path.read_text())
            if cached["reuse_key"] != key:
                raise InputError("Cannot combine stale prediction artifacts")
            completed.append(PredictionClip.model_validate(cached["prediction"]))
    predictions = Predictions(
        source="footlytics",
        generated_at=datetime.now(UTC),
        dataset_sha256=key["dataset_sha256"],
        pipeline_config=config,
        software_versions={
            k: str(v) for k, v in machine["versions"].items() if v is not None
        },
        model_weights=FileRef(
            path=Path(os.path.relpath(weights, out)).as_posix(),
            sha256=key["weights_sha256"],
        ),
        source_revision=revision,
        clips=completed,
    )
    target = out / "predictions.json"
    temporary = out / "predictions.json.partial"
    temporary.write_text(predictions.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(target)
    print(
        f"Prediction manifest: {target}; "
        f"completed {len(completed)}/{len(dataset.clips)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
