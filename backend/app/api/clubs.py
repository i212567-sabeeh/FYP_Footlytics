from fastapi import APIRouter, Response

from app.api.pagination import PaginationQuery
from app.auth.club_access import RosterEditor, ensure_club_access
from app.auth.dependencies import AdminUser, CurrentUser
from app.database.dependencies import DatabaseSession
from app.schemas.football import (
    ClubCreate,
    ClubMembershipCreate,
    ClubMembershipRead,
    ClubRead,
    ClubUpdate,
    Identifier,
    Page,
    UserReference,
)
from app.services import club_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=Page[ClubRead])
def list_clubs(
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
    active: bool | None = None,
):
    return club_service.list_clubs(session, user, page.offset, page.limit, active)


@router.post("", response_model=ClubRead, status_code=201)
def create_club(data: ClubCreate, session: DatabaseSession, admin: AdminUser):
    return club_service.create_club(session, data)


@router.get("/{club_id}", response_model=ClubRead)
def get_club(club_id: Identifier, session: DatabaseSession, user: CurrentUser):
    return ensure_club_access(session, user, club_id)


@router.patch("/{club_id}", response_model=ClubRead)
def update_club(
    club_id: Identifier, data: ClubUpdate, session: DatabaseSession, admin: AdminUser
):
    return club_service.update_club(session, admin, club_id, data)


@router.get("/{club_id}/members", response_model=Page[ClubMembershipRead])
def list_members(
    club_id: Identifier,
    session: DatabaseSession,
    admin: AdminUser,
    page: PaginationQuery,
):
    return club_service.list_members(session, admin, club_id, page.offset, page.limit)


@router.post("/{club_id}/members", response_model=ClubMembershipRead, status_code=201)
def add_member(
    club_id: Identifier,
    data: ClubMembershipCreate,
    session: DatabaseSession,
    admin: AdminUser,
):
    return club_service.add_member(session, admin, club_id, data.user_id)


@router.delete("/{club_id}/members/{user_id}", status_code=204)
def remove_member(
    club_id: Identifier, user_id: Identifier, session: DatabaseSession, admin: AdminUser
):
    club_service.remove_member(session, admin, club_id, user_id)
    return Response(status_code=204)


@router.get("/{club_id}/player-account-options", response_model=Page[UserReference])
def account_options(
    club_id: Identifier,
    session: DatabaseSession,
    user: RosterEditor,
    page: PaginationQuery,
):
    return club_service.account_options(session, user, club_id, page.offset, page.limit)
