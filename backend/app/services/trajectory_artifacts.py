"""Separate, attempt-specific cleaned trajectories with raw observation audit data."""

from app.cv.trajectory import TrajectoryObservation
from app.services.detection_artifacts import DetectionArtifact

COLUMNS = (
    "source_row_number",
    "frame_number",
    "timestamp_seconds",
    "track_id",
    "segment_id",
    "x1",
    "y1",
    "x2",
    "y2",
    "confidence",
    "pixel_x",
    "pixel_y",
    "raw_pitch_x",
    "raw_pitch_y",
    "clean_pitch_x",
    "clean_pitch_y",
    "inside_pitch",
    "usable",
    "status",
    "is_interpolated",
)


class TrajectoryArtifact(DetectionArtifact):
    columns = COLUMNS

    def write_observation(self, point: TrajectoryObservation) -> None:
        row = point.raw
        self.writer.writerow(
            (
                row.source_row,
                row.frame,
                row.timestamp,
                row.track_id,
                point.segment_id,
                *row.box,
                row.confidence,
                *row.pixel,
                *row.pitch,
                *(point.clean if point.clean is not None else (None, None)),
                "true" if row.inside_pitch else "false",
                "true" if point.usable else "false",
                point.status,
                "false",
            )
        )
