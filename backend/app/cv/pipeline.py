"""Detection-only streaming pipeline, invoked by the background worker."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.cv.detector import BaseDetector, Detection, DetectionError, is_reported
from app.cv.roi import PitchROI
from app.cv.video import VideoFrame, VideoFrames


@dataclass(frozen=True)
class DetectionRun:
    processed_frames: int
    decoded_frames: int
    total_detections: int  # Reported: confidence >= YOLO_CONFIDENCE.
    timestamp_fallback_frames: int
    low_confidence_detections: int = 0  # Stored only as ByteTrack candidates.


def detect_video(
    path: Path,
    detector: BaseDetector,
    *,
    stride: int,
    image_width: int,
    image_height: int,
    roi: PitchROI | None,
    confidence_threshold: float,
    write_frame: Callable[[VideoFrame, list[Detection]], None],
    progress: Callable[[int, int | None], None],
) -> DetectionRun:
    if stride < 1:
        raise ValueError("Frame stride must be positive")
    processed = total = low = estimated = 0
    with VideoFrames(path) as frames:
        for frame in frames:
            if frame.image.shape[:2] != (image_height, image_width):
                raise DetectionError(
                    "Video frame dimensions changed. Recalibrate the active source "
                    "before detection."
                )
            if frame.number % stride == 0:
                detections = detector.detect(frame.image)
                if roi is not None:
                    detections = [item for item in detections if roi.contains(item)]
                write_frame(frame, detections)
                processed += 1
                reported = sum(
                    is_reported(item.confidence, confidence_threshold)
                    for item in detections
                )
                total += reported
                low += len(detections) - reported
                estimated += int(frame.timestamp_estimated)
            progress(frames.decoded_frames, frames.total_frames)
    return DetectionRun(processed, frames.decoded_frames, total, estimated, low)
