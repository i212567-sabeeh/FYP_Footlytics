from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.auth.roles import RoleName
from app.models.user import User

NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda value: value.lower())]
FullName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
NewPassword = Annotated[SecretStr, Field(min_length=8, max_length=128)]


def unique_roles(roles: list[RoleName]) -> list[RoleName]:
    if len(set(roles)) != len(roles):
        raise ValueError("Roles must not contain duplicates")
    return roles


RoleList = Annotated[
    list[RoleName], Field(min_length=1, max_length=5), AfterValidator(unique_roles)
]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail
    full_name: FullName
    password: NewPassword
    roles: RoleList


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail | None = None
    full_name: FullName | None = None
    is_active: bool | None = None
    roles: RoleList | None = None

    @field_validator("email", "full_name", "is_active", "roles")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit unchanged fields instead of sending null")
        return value

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to update")
        return self


class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    roles: list[RoleName]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            roles=sorted(RoleName(role.name) for role in user.roles),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class UserList(BaseModel):
    items: list[UserRead]
    total: int
    offset: int
    limit: int
