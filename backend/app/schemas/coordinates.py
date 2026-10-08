from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.core.jobs import JobStatus
from app.schemas.football import ReadModel


class CoordinateSummary(ReadModel):
    total_rows: int = Field(ge=0)
    valid_mapped_rows: int = Field(ge=0)
    skipped_invalid_boxes: int = Field(ge=0)
    inside_pitch_rows: int = Field(ge=0)
    outside_pitch_rows: int = Field(ge=0)
    unique_tracks: int = Field(ge=0)
    first_frame: int | None = Field(ge=0)
    last_frame: int | None = Field(ge=0)
    tracking_job_id: int = Field(gt=0)
    tracking_attempt: int = Field(ge=0)
    calibration_id: int = Field(gt=0)
    calibration_updated_at: datetime
    pitch_length_metres: float = Field(gt=0, allow_inf_nan=False)
    pitch_width_metres: float = Field(gt=0, allow_inf_nan=False)
    bounds_tolerance_metres: float = Field(ge=0, le=1e-6, allow_inf_nan=False)
    coordinate_unit: Literal["metres"] = "metres"
    x_axis: Literal["length"] = "length"
    y_axis: Literal["width"] = "width"
    method: Literal["bbox_bottom_center_homography"] = "bbox_bottom_center_homography"
    artifact_format: Literal["csv"] = "csv"

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.total_rows != self.valid_mapped_rows + self.skipped_invalid_boxes
            or self.valid_mapped_rows
            != self.inside_pitch_rows + self.outside_pitch_rows
            or self.unique_tracks > self.valid_mapped_rows
            or self.pitch_length_metres < self.pitch_width_metres
        ):
            raise ValueError("Inconsistent coordinate summary")
        if self.valid_mapped_rows:
            if (
                self.unique_tracks == 0
                or self.first_frame is None
                or self.last_frame is None
                or self.last_frame < self.first_frame
            ):
                raise ValueError("Invalid mapped frame range")
        elif (
            self.first_frame is not None
            or self.last_frame is not None
            or self.unique_tracks
        ):
            raise ValueError("Empty coordinates must have no mapped frame range")
        return self


class CoordinateResultRead(CoordinateSummary):
    job_id: int
    job_updated_at: datetime
    status: JobStatus
    video_id: int
