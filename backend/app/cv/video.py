"""Incremental local video reads and explicit timestamp provenance."""

import math
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2

from app.cv.detector import DetectionError, Image
from app.services.video_decode import valid_metadata


@dataclass(frozen=True)
class VideoFrame:
    number: int
    timestamp_seconds: float
    image: Image
    timestamp_estimated: bool


class VideoFrames:
    def __init__(self, path: Path):
        self.path = path
        self.capture = cv2.VideoCapture()
        self.total_frames: int | None = None
        self.decoded_frames = 0

    def __enter__(self) -> "VideoFrames":
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "format_whitelist;mov|protocol_whitelist;file"
        )
        os.environ["OPENCV_FFMPEG_THREADS"] = "1"
        try:
            if not self.capture.open(str(self.path), cv2.CAP_FFMPEG):
                raise DetectionError(
                    "The stored video could not be opened for detection."
                )
            self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
            count = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
            self.total_frames = (
                int(count) if math.isfinite(count) and count >= 1 else None
            )
            if not valid_metadata(
                int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                self.fps,
                self.total_frames / self.fps
                if self.total_frames and self.fps > 0
                else 1,
            ):
                raise DetectionError("The stored video's frame metadata is invalid.")
            return self
        except Exception:
            self.capture.release()
            raise

    def __exit__(self, *_exc) -> None:
        self.capture.release()

    def __iter__(self) -> Iterator[VideoFrame]:
        previous_timestamp = -1.0
        while True:
            readable, image = self.capture.read()
            if not readable:
                if not self.decoded_frames:
                    raise DetectionError("The stored video has no readable frames.")
                if self.total_frames and self.decoded_frames < self.total_frames:
                    raise DetectionError(
                        "The video ended before its reported frame count. "
                        "Check the source and retry."
                    )
                return
            if image is None or not image.size:
                raise DetectionError("A video frame could not be decoded.")
            number = self.decoded_frames
            self.decoded_frames += 1
            timestamp = float(self.capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            estimated = (
                not math.isfinite(timestamp)
                or timestamp < 0
                or timestamp <= previous_timestamp
            )
            if estimated:
                timestamp = number / self.fps
            if timestamp <= previous_timestamp:
                raise DetectionError(
                    "Video timestamps are inconsistent. "
                    "Re-encode the source before detection."
                )
            previous_timestamp = timestamp
            yield VideoFrame(number, timestamp, image, estimated)
