from fastapi import APIRouter

from app.api.pagination import PaginationQuery
from app.auth.club_access import MatchEditor
from app.auth.dependencies import CurrentUser
from app.core.domain import MatchFormat
from app.database.dependencies import DatabaseSession
from app.schemas.football import Identifier, MatchCreate, MatchRead, MatchUpdate, Page
from app.services import match_service

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=Page[MatchRead])
def list_matches(
    session: DatabaseSession,
    user: CurrentUser,
    page: PaginationQuery,
    club_id: Identifier | None = None,
    team_id: Identifier | None = None,
    match_format: MatchFormat | None = None,
    archived: bool | None = None,
):
    return match_service.list_matches(
        session, user, club_id, team_id, match_format, archived, page.offset, page.limit
    )


@router.post("", response_model=MatchRead, status_code=201)
def create_match(data: MatchCreate, session: DatabaseSession, user: MatchEditor):
    return match_service.create_match(session, user, data)


@router.get("/{match_id}", response_model=MatchRead)
def get_match(match_id: Identifier, session: DatabaseSession, user: CurrentUser):
    return match_service.get_match(session, user, match_id)


@router.patch("/{match_id}", response_model=MatchRead)
def update_match(
    match_id: Identifier, data: MatchUpdate, session: DatabaseSession, user: MatchEditor
):
    return match_service.update_match(session, user, match_id, data)
