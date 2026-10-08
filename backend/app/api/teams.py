from fastapi import APIRouter, Response

from app.api.pagination import PaginationQuery
from app.auth.club_access import RosterEditor
from app.auth.dependencies import CurrentUser
from app.database.dependencies import DatabaseSession
from app.schemas.football import (
    Identifier,
    Page,
    SquadMembershipCreate,
    SquadMembershipRead,
    SquadMembershipUpdate,
    TeamCreate,
    TeamRead,
    TeamUpdate,
)
from app.services import squad_service, team_service

router = APIRouter(prefix="/teams", tags=["teams and squads"])


@router.get("", response_model=Page[TeamRead])
def list_teams(
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
    club_id: Identifier | None = None,
    active: bool | None = None,
):
    return team_service.list_teams(
        session, user, club_id, active, page.offset, page.limit
    )


@router.post("", response_model=TeamRead, status_code=201)
def create_team(data: TeamCreate, session: DatabaseSession, user: RosterEditor):
    return team_service.create_team(session, user, data)


@router.get("/{team_id}", response_model=TeamRead)
def get_team(team_id: Identifier, session: DatabaseSession, user: CurrentUser):
    return team_service.get_team(session, user, team_id)


@router.patch("/{team_id}", response_model=TeamRead)
def update_team(
    team_id: Identifier, data: TeamUpdate, session: DatabaseSession, user: RosterEditor
):
    return team_service.update_team(session, user, team_id, data)


@router.get("/{team_id}/squad", response_model=Page[SquadMembershipRead])
def list_squad(
    team_id: Identifier,
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
    active: bool | None = None,
):
    return squad_service.list_squad(
        session, user, team_id, active, page.offset, page.limit
    )


@router.post("/{team_id}/squad", response_model=SquadMembershipRead, status_code=201)
def add_player(
    team_id: Identifier,
    data: SquadMembershipCreate,
    session: DatabaseSession,
    user: RosterEditor,
):
    return squad_service.add_to_squad(session, user, team_id, data)


@router.patch("/{team_id}/squad/{membership_id}", response_model=SquadMembershipRead)
def update_membership(
    team_id: Identifier,
    membership_id: Identifier,
    data: SquadMembershipUpdate,
    session: DatabaseSession,
    user: RosterEditor,
):
    return squad_service.update_membership(session, user, team_id, membership_id, data)


@router.delete("/{team_id}/squad/{membership_id}", status_code=204)
def remove_membership(
    team_id: Identifier,
    membership_id: Identifier,
    session: DatabaseSession,
    user: RosterEditor,
):
    squad_service.update_membership(
        session, user, team_id, membership_id, SquadMembershipUpdate(is_active=False)
    )
    return Response(status_code=204)
