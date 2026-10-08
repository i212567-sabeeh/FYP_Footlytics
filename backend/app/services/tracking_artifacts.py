"""Track rows share the existing attempt-safe, atomic CSV publication lifecycle."""

from collections.abc import Sequence

from app.cv.tracker import TrackedDetection
from app.services.detection_artifacts import DetectionArtifact

COLUMNS = (
    "frame_number",
    "timestamp_seconds",
    "track_id",
    "x1",
    "y1",
    "x2",
    "y2",
    "confidence",
)


class TrackingArtifact(DetectionArtifact):
    columns = COLUMNS

    def write_tracks(
        self,
        frame_number: int,
        timestamp_seconds: float,
        tracks: Sequence[TrackedDetection],
    ) -> None:
        for track in tracks:
            self.writer.writerow(
                (
                    frame_number,
                    timestamp_seconds,
                    track.track_id,
                    *track.bbox,
                    track.confidence,
                )
            )
