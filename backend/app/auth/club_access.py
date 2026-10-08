"""Shared role capabilities and SQL scopes for lists and detail lookups."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.roles import RoleName
from app.models.football import (
    Club,
    ClubMembership,
    Match,
    Player,
    SquadMembership,
    Team,
)
from app.models.user import User
from app.services.domain_common import DomainError

ROSTER_ROLES = (RoleName.ADMIN, RoleName.COACH)
MATCH_ROLES = (*ROSTER_ROLES, RoleName.ANALYST)
STAFF_ROLES = (*MATCH_ROLES, RoleName.CLUB_MANAGEMENT)
RosterEditor = Annotated[User, Depends(require_roles(*ROSTER_ROLES))]
MatchEditor = Annotated[User, Depends(require_roles(*MATCH_ROLES))]


def has_roles(user: User, roles) -> bool:
    return bool(set(roles).intersection(role.name for role in user.roles))


def is_admin(user: User) -> bool:
    return has_roles(user, (RoleName.ADMIN,))


def is_player_only(user: User) -> bool:
    return not has_roles(user, STAFF_ROLES)


def visible_club_ids(user: User):
    statement = select(Club.id)
    if is_admin(user):
        return statement
    statement = statement.where(
        Club.is_active.is_(True),
        Club.id.in_(
            select(ClubMembership.club_id).where(ClubMembership.user_id == user.id)
        ),
    )
    if is_player_only(user):
        if not has_roles(user, (RoleName.PLAYER,)):
            return statement.where(false())
        statement = statement.where(
            Club.id.in_(
                select(Player.club_id).where(
                    Player.user_id == user.id, Player.is_active.is_(True)
                )
            )
        )
    return statement


def club_scope(user: User, club_column):
    return true() if is_admin(user) else club_column.in_(visible_club_ids(user))


def own_team_ids(user: User):
    return (
        select(SquadMembership.team_id)
        .join(Player, Player.id == SquadMembership.player_id)
        .join(Team, Team.id == SquadMembership.team_id)
        .where(
            Player.user_id == user.id,
            Player.is_active.is_(True),
            SquadMembership.is_active.is_(True),
            Team.is_active.is_(True),
        )
    )


def team_scope(user: User):
    condition = club_scope(user, Team.club_id)
    return (
        condition & Team.id.in_(own_team_ids(user))
        if is_player_only(user)
        else condition
    )


def player_scope(user: User):
    condition = club_scope(user, Player.club_id)
    return (
        condition & (Player.user_id == user.id) & Player.is_active.is_(True)
        if is_player_only(user)
        else condition
    )


def match_scope(user: User):
    condition = club_scope(user, Match.club_id)
    if is_player_only(user):
        condition &= or_(
            Match.team_a_id.in_(own_team_ids(user)),
            Match.team_b_id.in_(own_team_ids(user)),
        )
    return condition


def ensure_club_access(
    session: Session, user: User, club_id: int, *, write: bool = False
) -> Club:
    club = session.scalar(
        select(Club).where(Club.id == club_id, club_scope(user, Club.id))
    )
    if club is None:
        raise DomainError(404, "Club not found")
    if write and not club.is_active:
        raise DomainError(409, "Reactivate the club before changing its records")
    return club
