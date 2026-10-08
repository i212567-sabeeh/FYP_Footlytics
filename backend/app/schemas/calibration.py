from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.schemas.football import Identifier, ReadModel, RequestModel

Coordinate = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Point(RequestModel):
    x: Coordinate
    y: Coordinate


class CalibrationWrite(RequestModel):
    # Required to reject points selected on a frame of a since-replaced video.
    video_id: Identifier
    source_timestamp_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0
    image_points: Annotated[list[Point], Field(min_length=4, max_length=64)]
    pitch_points: Annotated[list[Point], Field(min_length=4, max_length=64)]

    @model_validator(mode="after")
    def matching_lengths(self) -> Self:
        if len(self.image_points) != len(self.pitch_points):
            raise ValueError("Image and pitch point lists must have the same length")
        return self


class PitchCalibrationRead(ReadModel):
    id: int
    match_id: int
    video_id: int
    source_frame_number: int
    source_timestamp_seconds: float
    image_width: int
    image_height: int
    pitch_length_metres: float
    pitch_width_metres: float
    image_points: list[Point]
    pitch_points: list[Point]
    homography_matrix: list[list[float]]
    reprojection_error: float = Field(
        description="Mean Euclidean residual over all supplied pairs, in metres"
    )
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
