"""Replaceable image-space tracking; one fresh tracker per match/job attempt."""

import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count
from types import SimpleNamespace

import numpy as np

from app.core.config import Settings
from app.cv.detector import Detection


class TrackingError(Exception):
    """Only curated, path-free messages may be persisted by a worker."""


@dataclass(frozen=True)
class TrackedDetection:
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float


class BaseTracker(ABC):
    @abstractmethod
    def update(self, detections: Sequence[Detection]) -> list[TrackedDetection]:
        """Advance exactly one sampled frame, including frames without detections."""


class ByteTrackTracker(BaseTracker):
    def __init__(
        self,
        settings: Settings,
        *,
        match_id: int,
        image_width: int,
        image_height: int,
        frame_stride: int = 1,
    ):
        if min(match_id, image_width, image_height, frame_stride) < 1:
            raise TrackingError(
                "Tracking requires a match, valid image dimensions and frame stride."
            )
        self.match_id = match_id
        self.width, self.height = image_width, image_height
        # ByteTrack ages a lost track once per update(), i.e. per sampled frame,
        # while TRACK_BUFFER counts source frames. Converting it keeps lost-track
        # memory to about the same source-frame span at any stride; stride 1 is
        # unchanged. Upstream keeps a removed track for one more association, so
        # buffers 0 and 1 behave alike and 1 is the recorded minimum.
        self.track_buffer_updates = max(1, settings.track_buffer // frame_stride)
        # Keep the API import lightweight. Never install packages inside a job.
        os.environ["YOLO_AUTOINSTALL"] = "false"
        try:
            from ultralytics.engine.results import Boxes
            from ultralytics.trackers.byte_tracker import BYTETracker, STrack

            # Ultralytics normally shares a global ID counter. A private track class
            # keeps even interleaved match jobs independent without patching globals.
            identifiers = count(1)

            class MatchTrack(STrack):
                @staticmethod
                def next_id() -> int:
                    return next(identifiers)

            class MatchByteTracker(BYTETracker):
                @staticmethod
                def reset_id() -> None:
                    pass  # Each wrapper owns a fresh counter; do not reset globals.

                def init_track(self, results, img=None):
                    return [
                        MatchTrack(np.append(box, index), score, cls)
                        for index, (box, score, cls) in enumerate(
                            zip(results.xywh, results.conf, results.cls, strict=True)
                        )
                    ]

            self._boxes = Boxes
            self._tracker = MatchByteTracker(
                SimpleNamespace(
                    track_high_thresh=settings.track_high_thresh,
                    track_low_thresh=settings.track_low_thresh,
                    new_track_thresh=settings.track_high_thresh,
                    match_thresh=settings.track_match_thresh,
                    track_buffer=self.track_buffer_updates,
                    fuse_score=True,
                )
            )
        except Exception as error:
            raise TrackingError(
                "ByteTrack could not initialize. "
                "Check the worker tracking dependencies."
            ) from error

    def update(self, detections: Sequence[Detection]) -> list[TrackedDetection]:
        rows = []
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox
            if (
                not np.isfinite((*detection.bbox, detection.confidence)).all()
                or not (0 <= x1 < x2 <= self.width and 0 <= y1 < y2 <= self.height)
                or not 0 <= detection.confidence <= 1
                or detection.class_name != "person"
            ):
                raise TrackingError("Detection data contains an invalid person box.")
            rows.append((*detection.bbox, detection.confidence, 0))
        boxes = self._boxes(
            np.asarray(rows, dtype=np.float32).reshape(-1, 6),
            orig_shape=(self.height, self.width),
        )
        try:
            result = self._tracker.update(boxes)
        except Exception as error:
            raise TrackingError(
                "ByteTrack failed while associating detections."
            ) from error
        tracks = []
        for row in result:
            if len(row) != 8 or not np.isfinite(row).all() or row[4] < 1:
                raise TrackingError("ByteTrack returned invalid tracking data.")
            # Kalman updates remain in pixels and may cross an image edge slightly.
            x1, x2 = np.clip(row[[0, 2]], 0, self.width)
            y1, y2 = np.clip(row[[1, 3]], 0, self.height)
            if x1 >= x2 or y1 >= y2 or not 0 <= row[5] <= 1:
                raise TrackingError("ByteTrack returned an invalid tracking box.")
            tracks.append(
                TrackedDetection(
                    int(row[4]), tuple(map(float, (x1, y1, x2, y2))), float(row[5])
                )
            )
        return tracks
