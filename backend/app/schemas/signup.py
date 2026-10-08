from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.auth.roles import SignupRole
from app.models.signup_request import SignupStatus
from app.schemas.football import Identifier, ReadModel, RequestModel
from app.schemas.user import FullName, NewPassword, NormalizedEmail


class SignupCreate(RequestModel):
    email: NormalizedEmail
    full_name: FullName
    password: NewPassword
    requested_role: SignupRole


class SignupReceipt(BaseModel):
    # Same response for new, existing and already-reviewed email addresses.
    message: str = (
        "New signup requests require administrator approval before sign-in. "
        "If you already have an account or request, contact your administrator."
    )


class SignupRequestRead(ReadModel):
    id: int
    email: str
    full_name: str
    requested_role: SignupRole | None
    status: SignupStatus
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by_user_id: int | None
    approved_user_id: int | None


class SignupApproval(RequestModel):
    roles: Annotated[list[SignupRole], Field(min_length=1, max_length=1)]
    club_id: Identifier | None = None
