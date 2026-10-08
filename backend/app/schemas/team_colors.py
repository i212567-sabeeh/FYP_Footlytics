"""Bounded, current-track crop selection. Colors themselves are measured server-side."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.football import Identifier, ReadModel, RequestModel

TeamColor = Literal["team_a", "team_b"]
Version = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Color = tuple[float, float, float]


class ColorSampleInput(RequestModel):
    team: TeamColor
    track_id: Identifier
    frame_number: Annotated[int, Field(ge=0, le=2**63 - 1)]


class TeamColorsSave(RequestModel):
    tracking_version: Version
    samples: Annotated[list[ColorSampleInput], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def distinct_teams(self) -> Self:
        if {sample.team for sample in self.samples} != {"team_a", "team_b"}:
            raise ValueError("Select at least one example for each team")
        if len({(s.track_id, s.frame_number) for s in self.samples}) != len(
            self.samples
        ):
            raise ValueError("Do not repeat a crop or assign it to both teams")
        assigned: dict[int, str] = {}
        for sample in self.samples:
            if assigned.setdefault(sample.track_id, sample.team) != sample.team:
                raise ValueError("A representative track cannot seed both teams")
        return self


class ColorSampleRead(ColorSampleInput, ReadModel):
    id: str
    color: Color
    quality: float = Field(ge=0, le=1, allow_inf_nan=False)


class ColorPrototypeRead(ReadModel):
    team: TeamColor
    color: Color
    quality: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_ids: list[str]


class TeamColorSetRead(ReadModel):
    id: int
    tracking_job_id: int
    samples: list[ColorSampleRead]
    prototypes: list[ColorPrototypeRead]
    classification_mode: Literal["user_seeded"] = "user_seeded"
    created_by_user_id: int
    created_at: datetime


class TeamColorsRead(ReadModel):
    tracking_job_id: int
    tracking_version: Version
    current: TeamColorSetRead | None


class ColorPreviewRead(ReadModel):
    track_id: int
    frame_number: int
    tracking_version: Version
    crop_data_url: str
    quality: float = Field(ge=0, le=1, allow_inf_nan=False)
    usable: bool
    rejection_reason: str | None
