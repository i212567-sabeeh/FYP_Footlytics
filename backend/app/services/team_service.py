from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access, team_scope
from app.models.football import Team
from app.models.user import User
from app.schemas.football import TeamCreate, TeamRead, TeamUpdate
from app.services.domain_common import (
    DomainError,
    apply_changes,
    commit_record,
    page_results,
)


def get_team(session: Session, user: User, team_id: int) -> Team:
    team = session.scalar(select(Team).where(Team.id == team_id, team_scope(user)))
    if team is None:
        raise DomainError(404, "Team not found")
    return team


def list_teams(
    session: Session,
    user: User,
    club_id: int | None,
    active: bool | None,
    offset: int,
    limit: int,
):
    statement = select(Team).where(team_scope(user)).order_by(Team.name, Team.id)
    if club_id is not None:
        ensure_club_access(session, user, club_id)
        statement = statement.where(Team.club_id == club_id)
    if active is not None:
        statement = statement.where(Team.is_active == active)
    return page_results(session, statement, TeamRead, offset, limit)


def create_team(session: Session, user: User, data: TeamCreate) -> Team:
    ensure_club_access(session, user, data.club_id, write=True)
    team = Team(**data.model_dump(), name_key=data.name.casefold())
    session.add(team)
    return commit_record(
        session, team, "A team with this name already exists in the club"
    )


def update_team(session: Session, user: User, team_id: int, data: TeamUpdate) -> Team:
    team = get_team(session, user, team_id)
    ensure_club_access(session, user, team.club_id, write=True)
    apply_changes(team, data.model_dump(exclude_unset=True))
    return commit_record(
        session, team, "A team with this name already exists in the club"
    )
