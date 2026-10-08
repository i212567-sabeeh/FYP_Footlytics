from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth.club_access import STAFF_ROLES
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier
from app.schemas.trajectories import TrajectoryResultRead
from app.services import trajectory_service

router = APIRouter(tags=["trajectories"])
TrajectoryReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.get(
    "/matches/{match_id}/trajectories/summary", response_model=TrajectoryResultRead
)
def get_summary(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: TrajectoryReader,
):
    return trajectory_service.get_summary(
        session, user, match_id, request.app.state.settings
    )
