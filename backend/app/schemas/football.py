from datetime import UTC, date, datetime
from typing import Annotated, ClassVar, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.domain import (
    MAX_PITCH_LENGTH,
    MAX_PITCH_WIDTH,
    MIN_PITCH_LENGTH,
    MIN_PITCH_WIDTH,
    MatchFormat,
    Position,
)

Identifier = Annotated[int, Field(gt=0, le=2**63 - 1)]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
PersonName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
ShirtNumber = Annotated[int, Field(ge=1, le=99)]
PitchLength = Annotated[
    float, Field(ge=MIN_PITCH_LENGTH, le=MAX_PITCH_LENGTH, allow_inf_nan=False)
]
PitchWidth = Annotated[
    float, Field(ge=MIN_PITCH_WIDTH, le=MAX_PITCH_WIDTH, allow_inf_nan=False)
]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatchModel(RequestModel):
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to update")
        for name in self.model_fields_set - self.nullable_fields:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null; omit unchanged fields")
        return self


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int


class UserReference(ReadModel):
    id: int
    full_name: str


class ClubReference(ReadModel):
    id: int
    name: str
    is_active: bool


class TeamReference(ClubReference):
    club_id: int


class ClubCreate(RequestModel):
    name: Name
    short_name: ShortName | None = None
    description: Description | None = None


class ClubUpdate(PatchModel):
    nullable_fields = frozenset({"short_name", "description"})
    name: Name | None = None
    short_name: ShortName | None = None
    description: Description | None = None
    is_active: bool | None = None


class ClubRead(ClubReference):
    short_name: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class ClubMembershipCreate(RequestModel):
    user_id: Identifier


class ClubMembershipRead(ReadModel):
    id: int
    club_id: int
    user_id: int
    user: UserReference
    created_at: datetime


class TeamCreate(ClubCreate):
    club_id: Identifier


class TeamUpdate(ClubUpdate):
    pass


class TeamRead(ClubRead):
    club_id: int
    club: ClubReference


class BirthDateValidation(RequestModel):
    date_of_birth: date | None = None

    @field_validator("date_of_birth")
    @classmethod
    def validate_birth_date(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(UTC).date():
            raise ValueError("Date of birth cannot be in the future")
        return value


class PlayerCreate(BirthDateValidation):
    club_id: Identifier
    user_id: Identifier | None = None
    first_name: PersonName
    last_name: PersonName
    display_name: Name | None = None
    preferred_position: Position | None = None


class PlayerUpdate(PatchModel, BirthDateValidation):
    nullable_fields = frozenset(
        {"user_id", "display_name", "date_of_birth", "preferred_position"}
    )
    user_id: Identifier | None = None
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    display_name: Name | None = None
    preferred_position: Position | None = None
    is_active: bool | None = None


class PlayerReference(ReadModel):
    id: int
    first_name: str
    last_name: str
    display_name: str | None
    preferred_position: Position | None
    is_active: bool


class PlayerRead(PlayerReference):
    club_id: int
    club: ClubReference
    user_id: int | None
    linked_user: UserReference | None
    date_of_birth: date | None
    created_at: datetime
    updated_at: datetime


class SquadMembershipCreate(RequestModel):
    player_id: Identifier
    shirt_number: ShirtNumber | None = None
    joined_at: AwareDatetime | None = None


class SquadMembershipUpdate(PatchModel):
    nullable_fields = frozenset({"shirt_number", "joined_at", "left_at"})
    shirt_number: ShirtNumber | None = None
    is_active: bool | None = None
    joined_at: AwareDatetime | None = None
    left_at: AwareDatetime | None = None


class SquadMembershipRead(ReadModel):
    id: int
    team_id: int
    player_id: int
    team: TeamReference
    player: PlayerReference
    shirt_number: int | None
    is_active: bool
    joined_at: datetime | None
    left_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MatchCreate(RequestModel):
    club_id: Identifier
    title: Name
    team_a_id: Identifier
    team_b_id: Identifier
    match_format: MatchFormat
    match_date: AwareDatetime
    pitch_length_metres: PitchLength
    pitch_width_metres: PitchWidth
    venue: Name | None = None
    notes: Notes | None = None

    @model_validator(mode="after")
    def validate_match(self) -> Self:
        if self.team_a_id == self.team_b_id:
            raise ValueError("Team A and Team B must be different")
        if self.pitch_length_metres < self.pitch_width_metres:
            raise ValueError("Pitch length must be at least its width")
        return self


class MatchUpdate(PatchModel):
    nullable_fields = frozenset({"venue", "notes"})
    title: Name | None = None
    team_a_id: Identifier | None = None
    team_b_id: Identifier | None = None
    match_format: MatchFormat | None = None
    match_date: AwareDatetime | None = None
    pitch_length_metres: PitchLength | None = None
    pitch_width_metres: PitchWidth | None = None
    venue: Name | None = None
    notes: Notes | None = None
    is_archived: bool | None = None


class MatchRead(ReadModel):
    id: int
    club_id: int
    club: ClubReference
    title: str
    team_a_id: int
    team_b_id: int
    team_a: TeamReference
    team_b: TeamReference
    match_format: MatchFormat
    match_date: datetime
    pitch_length_metres: float
    pitch_width_metres: float
    venue: str | None
    notes: str | None
    is_archived: bool
    created_by_user_id: int
    created_by: UserReference
    created_at: datetime
    updated_at: datetime
