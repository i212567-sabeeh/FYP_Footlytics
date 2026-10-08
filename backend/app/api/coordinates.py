from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.club_access import STAFF_ROLES
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.coordinates import CoordinateResultRead
from app.schemas.football import Identifier
from app.services import coordinate_service

router = APIRouter(tags=["pitch coordinates"])
CoordinateReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.get(
    "/matches/{match_id}/coordinates/summary", response_model=CoordinateResultRead
)
def get_summary(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: CoordinateReader,
):
    return coordinate_service.get_summary(
        session, user, match_id, request.app.state.settings
    )
