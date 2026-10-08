from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import club_scope, ensure_club_access
from app.models.football import Club, ClubMembership, Player
from app.models.user import User
from app.schemas.football import (
    ClubCreate,
    ClubMembershipRead,
    ClubRead,
    ClubUpdate,
    UserReference,
)
from app.services.domain_common import (
    DomainError,
    apply_changes,
    commit_record,
    page_results,
)


def list_clubs(
    session: Session, user: User, offset: int, limit: int, active: bool | None = None
):
    statement = select(Club).where(club_scope(user, Club.id))
    if active is not None:
        statement = statement.where(Club.is_active == active)
    return page_results(
        session,
        statement.order_by(Club.name, Club.id),
        ClubRead,
        offset,
        limit,
    )


def create_club(session: Session, data: ClubCreate) -> Club:
    club = Club(**data.model_dump(), name_key=data.name.casefold())
    session.add(club)
    return commit_record(session, club, "A club with this name already exists")


def update_club(session: Session, user: User, club_id: int, data: ClubUpdate) -> Club:
    club = ensure_club_access(session, user, club_id)
    apply_changes(club, data.model_dump(exclude_unset=True))
    return commit_record(session, club, "A club with this name already exists")


def list_members(session: Session, user: User, club_id: int, offset: int, limit: int):
    ensure_club_access(session, user, club_id)
    return page_results(
        session,
        select(ClubMembership)
        .where(ClubMembership.club_id == club_id)
        .order_by(ClubMembership.id),
        ClubMembershipRead,
        offset,
        limit,
    )


def add_member(
    session: Session, user: User, club_id: int, user_id: int
) -> ClubMembership:
    ensure_club_access(session, user, club_id, write=True)
    member = session.get(User, user_id)
    if member is None or not member.is_active:
        raise DomainError(422, "Choose an existing active user")
    membership = ClubMembership(club_id=club_id, user_id=user_id)
    session.add(membership)
    return commit_record(session, membership, "User is already a member of this club")


def remove_member(session: Session, user: User, club_id: int, user_id: int) -> None:
    ensure_club_access(session, user, club_id)
    membership = session.scalar(
        select(ClubMembership).where(
            ClubMembership.club_id == club_id, ClubMembership.user_id == user_id
        )
    )
    if membership is None:
        raise DomainError(404, "Club membership not found")
    session.delete(membership)
    session.commit()


def account_options(
    session: Session, user: User, club_id: int, offset: int, limit: int
):
    ensure_club_access(session, user, club_id)
    statement = (
        select(User)
        .join(ClubMembership)
        .where(
            ClubMembership.club_id == club_id,
            User.is_active.is_(True),
            ~User.id.in_(select(Player.user_id).where(Player.user_id.is_not(None))),
        )
        .order_by(User.full_name, User.id)
    )
    return page_results(session, statement, UserReference, offset, limit)
