from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.core.jobs import JobStatus
from app.schemas.football import ReadModel


class TrajectorySummary(ReadModel):
    source_rows: int = Field(ge=0)
    usable_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    outside_pitch_rows: int = Field(ge=0)
    jump_outlier_rows: int = Field(ge=0)
    invalid_temporal_rows: int = Field(ge=0)
    interpolated_rows: Literal[0] = 0
    smoothed_rows: int = Field(ge=0)
    unique_tracks: int = Field(ge=0)
    segments: int = Field(ge=0)
    first_frame: int | None = Field(ge=0)
    last_frame: int | None = Field(ge=0)
    coordinate_job_id: int = Field(gt=0)
    coordinate_attempt: int = Field(ge=0)
    pitch_length_metres: float = Field(gt=0, allow_inf_nan=False)
    pitch_width_metres: float = Field(gt=0, allow_inf_nan=False)
    max_plausible_speed_mps: float = Field(gt=0, le=100, allow_inf_nan=False)
    max_gap_seconds: float = Field(gt=0, le=60, allow_inf_nan=False)
    smoothing_window: int = Field(ge=1, le=11)
    smoothing_max_shift_metres: float = Field(ge=0, le=5, allow_inf_nan=False)
    interpolation_policy: Literal["none_preserve_gaps"] = "none_preserve_gaps"
    method: Literal["neighbor_filter_time_residual_median_v1"] = (
        "neighbor_filter_time_residual_median_v1"
    )
    coordinate_unit: Literal["metres"] = "metres"
    artifact_format: Literal["csv"] = "csv"

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if (
            self.source_rows != self.usable_rows + self.rejected_rows
            or self.rejected_rows
            != self.outside_pitch_rows
            + self.jump_outlier_rows
            + self.invalid_temporal_rows
            or self.smoothed_rows > self.usable_rows
            or self.segments > self.usable_rows
            or bool(self.segments) != bool(self.usable_rows)
            or self.unique_tracks > self.source_rows
            or self.smoothing_window % 2 != 1
            or self.pitch_length_metres < self.pitch_width_metres
        ):
            raise ValueError("Inconsistent trajectory summary")
        if self.source_rows:
            if (
                not self.unique_tracks
                or self.first_frame is None
                or self.last_frame is None
                or self.first_frame > self.last_frame
            ):
                raise ValueError("Invalid trajectory frame range")
        elif (
            self.unique_tracks
            or self.first_frame is not None
            or self.last_frame is not None
        ):
            raise ValueError("Empty trajectories must have an empty frame range")
        return self


class TrajectoryResultRead(TrajectorySummary):
    job_id: int
    job_updated_at: datetime
    status: JobStatus
    video_id: int
