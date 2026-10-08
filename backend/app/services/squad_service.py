from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access, is_player_only
from app.database.base import utc_now
from app.models.football import Player, SquadMembership
from app.models.user import User
from app.schemas.football import (
    SquadMembershipCreate,
    SquadMembershipRead,
    SquadMembershipUpdate,
)
from app.services.domain_common import (
    DomainError,
    apply_changes,
    commit_record,
    page_results,
)
from app.services.team_service import get_team


def list_squad(
    session: Session,
    user: User,
    team_id: int,
    active: bool | None,
    offset: int,
    limit: int,
):
    get_team(session, user, team_id)
    statement = (
        select(SquadMembership)
        .where(SquadMembership.team_id == team_id)
        .order_by(SquadMembership.id)
    )
    if is_player_only(user):
        statement = statement.where(
            SquadMembership.player_id.in_(
                select(Player.id).where(Player.user_id == user.id)
            ),
            SquadMembership.is_active.is_(True),
        )
    if active is not None:
        statement = statement.where(SquadMembership.is_active == active)
    return page_results(session, statement, SquadMembershipRead, offset, limit)


def add_to_squad(
    session: Session, user: User, team_id: int, data: SquadMembershipCreate
) -> SquadMembership:
    team = get_team(session, user, team_id)
    ensure_club_access(session, user, team.club_id, write=True)
    player = session.scalar(
        select(Player).where(
            Player.id == data.player_id, Player.club_id == team.club_id
        )
    )
    if player is None or not player.is_active or not team.is_active:
        raise DomainError(
            422,
            "Choose an active team and an active football player from the same club",
        )
    membership = SquadMembership(
        club_id=team.club_id,
        team_id=team.id,
        player_id=player.id,
        shirt_number=data.shirt_number,
        joined_at=data.joined_at or utc_now(),
    )
    session.add(membership)
    return commit_record(
        session, membership, "Player or shirt number is already in this active squad"
    )


def update_membership(
    session: Session,
    user: User,
    team_id: int,
    membership_id: int,
    data: SquadMembershipUpdate,
) -> SquadMembership:
    team = get_team(session, user, team_id)
    ensure_club_access(session, user, team.club_id, write=True)
    membership = session.scalar(
        select(SquadMembership).where(
            SquadMembership.id == membership_id, SquadMembership.team_id == team.id
        )
    )
    if membership is None:
        raise DomainError(404, "Squad membership not found")
    if data.is_active is True and not membership.is_active:
        raise DomainError(
            409, "Add a new membership to rejoin; ended memberships remain history"
        )
    changes = data.model_dump(exclude_unset=True)
    if (
        changes.get("is_active") is False
        and membership.is_active
        and "left_at" not in changes
    ):
        changes["left_at"] = utc_now()
    active = changes.get("is_active", membership.is_active)
    joined = changes.get("joined_at", membership.joined_at)
    left = changes.get("left_at", membership.left_at)
    if active and left is not None:
        raise DomainError(422, "An active membership cannot have a leaving date")
    if left is not None and joined is not None and left < joined:
        raise DomainError(422, "Leaving date cannot precede joining date")
    apply_changes(membership, changes)
    return commit_record(
        session, membership, "Player or shirt number is already in this active squad"
    )
