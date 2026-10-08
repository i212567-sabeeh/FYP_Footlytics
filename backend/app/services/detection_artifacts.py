"""Stream CSV rows to an attempt-specific artifact; publish only complete output."""

import csv
import os
from uuid import uuid4

from app.core.config import Settings
from app.cv.detector import Detection
from app.cv.video import VideoFrame
from app.services.storage_service import StorageService

COLUMNS = (
    "frame_number",
    "timestamp_seconds",
    "x1",
    "y1",
    "x2",
    "y2",
    "confidence",
    "class_id",
    "class_name",
    "frame_width",
    "frame_height",
)


class DetectionArtifact:
    columns = COLUMNS

    def __init__(
        self,
        settings: Settings,
        match_id: int,
        video_id: int,
        job_id: int,
        attempt: int,
    ):
        if min(match_id, video_id, job_id) < 1 or attempt < 0:
            raise ValueError("Invalid artifact identifiers")
        self.storage = StorageService(settings)
        self.relative_path = (
            f"tracks/matches/{match_id}/videos/{video_id}/jobs/{job_id}/"
            f"attempt-{attempt}-{uuid4().hex}.csv"
        )
        self.path = self.storage.resolve(self.relative_path)
        self.temporary = self.storage.resolve(self.relative_path + ".partial")
        self.kept = False

    def __enter__(self) -> "DetectionArtifact":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.temporary.open("x", encoding="utf-8", newline="")
        try:
            self.writer = csv.writer(self.file)
            self.writer.writerow(self.columns)
        except Exception:
            self.file.close()
            self.storage.delete(self.relative_path + ".partial")
            raise
        return self

    def write_frame(self, frame: VideoFrame, detections: list[Detection]) -> None:
        height, width = frame.image.shape[:2]
        for detection in detections:
            self.writer.writerow(
                (
                    frame.number,
                    frame.timestamp_seconds,
                    *detection.bbox,
                    detection.confidence,
                    detection.class_id,
                    detection.class_name,
                    width,
                    height,
                )
            )

    def publish(self) -> str:
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        # Recheck redirected paths immediately before publication.
        os.replace(
            self.storage.resolve(self.relative_path + ".partial"),
            self.storage.resolve(self.relative_path),
        )
        return self.relative_path

    def keep(self) -> None:
        """Call only after the matching job attempt commits a successful result."""
        self.kept = True

    def __exit__(self, *_exc) -> None:
        self.file.close()
        if not self.kept:
            self.storage.delete(self.relative_path + ".partial")
            self.storage.delete(self.relative_path)
