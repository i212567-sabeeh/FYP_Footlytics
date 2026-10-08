from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import (
    ensure_club_access,
    is_player_only,
    own_team_ids,
    player_scope,
)
from app.models.football import ClubMembership, Player, SquadMembership
from app.models.user import User
from app.schemas.football import (
    PlayerCreate,
    PlayerRead,
    PlayerUpdate,
    SquadMembershipRead,
)
from app.services.domain_common import (
    DomainError,
    apply_changes,
    commit_record,
    page_results,
)
from app.services.team_service import get_team


def get_player(session: Session, user: User, player_id: int) -> Player:
    player = session.scalar(
        select(Player).where(Player.id == player_id, player_scope(user))
    )
    if player is None:
        raise DomainError(404, "Football player not found")
    return player


def list_players(
    session: Session,
    user: User,
    club_id: int | None,
    team_id: int | None,
    active: bool | None,
    offset: int,
    limit: int,
):
    statement = (
        select(Player)
        .where(player_scope(user))
        .order_by(Player.last_name, Player.first_name, Player.id)
    )
    if club_id is not None:
        ensure_club_access(session, user, club_id)
        statement = statement.where(Player.club_id == club_id)
    if team_id is not None:
        get_team(session, user, team_id)
        statement = statement.where(
            Player.id.in_(
                select(SquadMembership.player_id).where(
                    SquadMembership.team_id == team_id,
                    SquadMembership.is_active.is_(True),
                )
            )
        )
    if active is not None:
        statement = statement.where(Player.is_active == active)
    return page_results(session, statement, PlayerRead, offset, limit)


def validate_user_link(session: Session, club_id: int, user_id: int | None) -> None:
    if user_id is None:
        return
    linked = session.scalar(
        select(User)
        .join(ClubMembership)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            ClubMembership.club_id == club_id,
        )
    )
    if linked is None:
        raise DomainError(422, "Linked account must be an active member of this club")


def create_player(session: Session, user: User, data: PlayerCreate) -> Player:
    ensure_club_access(session, user, data.club_id, write=True)
    validate_user_link(session, data.club_id, data.user_id)
    player = Player(**data.model_dump())
    session.add(player)
    return commit_record(
        session, player, "The account is already linked to a football player"
    )


def update_player(
    session: Session, user: User, player_id: int, data: PlayerUpdate
) -> Player:
    player = get_player(session, user, player_id)
    ensure_club_access(session, user, player.club_id, write=True)
    changes = data.model_dump(exclude_unset=True)
    if "user_id" in changes and data.user_id != player.user_id:
        validate_user_link(session, player.club_id, data.user_id)
    apply_changes(player, changes)
    return commit_record(
        session, player, "The account is already linked to a football player"
    )


def memberships(session: Session, user: User, player_id: int, offset: int, limit: int):
    player = get_player(session, user, player_id)
    statement = (
        select(SquadMembership)
        .where(SquadMembership.player_id == player.id)
        .order_by(SquadMembership.id.desc())
    )
    if is_player_only(user):
        statement = statement.where(
            SquadMembership.is_active.is_(True),
            SquadMembership.team_id.in_(own_team_ids(user)),
        )
    return page_results(session, statement, SquadMembershipRead, offset, limit)
