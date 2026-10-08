from fastapi import APIRouter

from app.api.pagination import PaginationQuery
from app.auth.club_access import RosterEditor
from app.auth.dependencies import CurrentUser
from app.database.dependencies import DatabaseSession
from app.schemas.football import (
    Identifier,
    Page,
    PlayerCreate,
    PlayerRead,
    PlayerUpdate,
    SquadMembershipRead,
)
from app.services import player_service

router = APIRouter(prefix="/players", tags=["football players"])


@router.get("", response_model=Page[PlayerRead])
def list_players(
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
    club_id: Identifier | None = None,
    team_id: Identifier | None = None,
    active: bool | None = None,
):
    return player_service.list_players(
        session, user, club_id, team_id, active, page.offset, page.limit
    )


@router.post("", response_model=PlayerRead, status_code=201)
def create_player(data: PlayerCreate, session: DatabaseSession, user: RosterEditor):
    return player_service.create_player(session, user, data)


@router.get("/{player_id}", response_model=PlayerRead)
def get_player(player_id: Identifier, session: DatabaseSession, user: CurrentUser):
    return player_service.get_player(session, user, player_id)


@router.patch("/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: Identifier,
    data: PlayerUpdate,
    session: DatabaseSession,
    user: RosterEditor,
):
    return player_service.update_player(session, user, player_id, data)


@router.get("/{player_id}/squads", response_model=Page[SquadMembershipRead])
def memberships(
    player_id: Identifier,
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
):
    return player_service.memberships(session, user, player_id, page.offset, page.limit)
