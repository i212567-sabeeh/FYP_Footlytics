from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.pagination import PaginationQuery
from app.auth.club_access import STAFF_ROLES
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier, Page
from app.schemas.player_analytics import TrackAnalyticsRead, TrackHeatmapRead
from app.services import player_analytics_service as service

router = APIRouter(tags=["player analytics"])
AnalyticsReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.get(
    "/matches/{match_id}/player-analytics", response_model=Page[TrackAnalyticsRead]
)
def list_players(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: AnalyticsReader,
    page: PaginationQuery,
):
    return service.list_players(
        session, user, match_id, request.app.state.settings, page.offset, page.limit
    )


@router.get(
    "/matches/{match_id}/player-analytics/{track_id}", response_model=TrackAnalyticsRead
)
def get_player(
    match_id: Identifier,
    track_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: AnalyticsReader,
):
    return service.get_player(
        session, user, match_id, track_id, request.app.state.settings
    )


@router.get(
    "/matches/{match_id}/player-analytics/{track_id}/heatmap",
    response_model=TrackHeatmapRead,
)
def get_heatmap(
    match_id: Identifier,
    track_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: AnalyticsReader,
):
    return service.get_heatmap(
        session, user, match_id, track_id, request.app.state.settings
    )
