from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.pagination import PaginationQuery
from app.auth.club_access import STAFF_ROLES, MatchEditor
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier, Page
from app.schemas.team_assignment import TeamAssignmentRead, TeamOverride
from app.services import team_assignment_service

router = APIRouter(tags=["team assignments"])
AssignmentReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.get(
    "/matches/{match_id}/team-assignments", response_model=Page[TeamAssignmentRead]
)
def list_assignments(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: AssignmentReader,
    page: PaginationQuery,
):
    return team_assignment_service.list_assignments(
        session, user, match_id, request.app.state.settings, page.offset, page.limit
    )


@router.patch(
    "/matches/{match_id}/tracks/{track_id}/team", response_model=TeamAssignmentRead
)
def set_override(
    match_id: Identifier,
    track_id: Identifier,
    data: TeamOverride,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
):
    return team_assignment_service.set_override(
        session, user, match_id, track_id, data.team, request.app.state.settings
    )
