from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.pagination import PaginationQuery
from app.auth.club_access import STAFF_ROLES
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier, Page
from app.schemas.team_analytics import (
    TacticalTeam,
    TeamAnalyticsRead,
    TeamSnapshot,
    TeamTacticalSummary,
)
from app.services import team_analytics_service as service

router = APIRouter(tags=["team tactical analytics"])
TacticsReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.get("/matches/{match_id}/team-analytics", response_model=TeamAnalyticsRead)
def get_summary(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: TacticsReader,
):
    return service.get_summary(session, user, match_id, request.app.state.settings)


@router.get(
    "/matches/{match_id}/team-analytics/{team}", response_model=TeamTacticalSummary
)
def get_team(
    match_id: Identifier,
    team: TacticalTeam,
    request: Request,
    session: DatabaseSession,
    user: TacticsReader,
):
    return service.get_team(session, user, match_id, team, request.app.state.settings)


@router.get(
    "/matches/{match_id}/team-analytics/{team}/series",
    response_model=Page[TeamSnapshot],
)
def get_series(
    match_id: Identifier,
    team: TacticalTeam,
    request: Request,
    session: DatabaseSession,
    user: TacticsReader,
    page: PaginationQuery,
):
    return service.get_series(
        session,
        user,
        match_id,
        team,
        request.app.state.settings,
        page.offset,
        page.limit,
    )
