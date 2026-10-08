"""Coordinate CSVs reuse protected, attempt-specific atomic publication."""

from app.cv.player_position import PitchPosition
from app.cv.tracking_rows import TrackObservation
from app.services.detection_artifacts import DetectionArtifact
from app.services.tracking_artifacts import COLUMNS as TRACK_COLUMNS

COLUMNS = (*TRACK_COLUMNS, "pixel_x", "pixel_y", "pitch_x", "pitch_y", "inside_pitch")


class CoordinateArtifact(DetectionArtifact):
    columns = COLUMNS

    def write_position(self, row: TrackObservation, position: PitchPosition) -> None:
        self.writer.writerow(
            (
                row.frame,
                row.timestamp,
                row.track_id,
                *row.box,
                row.confidence,
                position.pixel_x,
                position.pixel_y,
                position.pitch_x,
                position.pitch_y,
                "true" if position.inside_pitch else "false",
            )
        )
