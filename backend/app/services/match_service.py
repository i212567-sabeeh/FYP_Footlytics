from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access, match_scope
from app.core.domain import MatchFormat
from app.models.football import Match, Team
from app.models.user import User
from app.schemas.football import MatchCreate, MatchRead, MatchUpdate
from app.services.domain_common import (
    DomainError,
    apply_changes,
    commit_record,
    page_results,
)
from app.services.team_service import get_team


def get_match(session: Session, user: User, match_id: int) -> Match:
    match = session.scalar(select(Match).where(Match.id == match_id, match_scope(user)))
    if match is None:
        raise DomainError(404, "Match not found")
    return match


def list_matches(
    session: Session,
    user: User,
    club_id: int | None,
    team_id: int | None,
    match_format: MatchFormat | None,
    archived: bool | None,
    offset: int,
    limit: int,
):
    statement = (
        select(Match)
        .where(match_scope(user))
        .order_by(Match.match_date.desc(), Match.id.desc())
    )
    if club_id is not None:
        ensure_club_access(session, user, club_id)
        statement = statement.where(Match.club_id == club_id)
    if team_id is not None:
        get_team(session, user, team_id)
        statement = statement.where(
            or_(Match.team_a_id == team_id, Match.team_b_id == team_id)
        )
    if match_format is not None:
        statement = statement.where(Match.match_format == match_format)
    if archived is not None:
        statement = statement.where(Match.is_archived == archived)
    return page_results(session, statement, MatchRead, offset, limit)


def validate_teams(
    session: Session, club_id: int, team_ids: list[int], require_active: set[int]
) -> None:
    if team_ids[0] == team_ids[1]:
        raise DomainError(422, "Team A and Team B must be different")
    teams = session.scalars(
        select(Team).where(Team.id.in_(team_ids), Team.club_id == club_id)
    ).all()
    if len(teams) != 2:
        raise DomainError(422, "Both teams must belong to the match club")
    if any(team.id in require_active and not team.is_active for team in teams):
        raise DomainError(422, "Choose active teams for a new match or team change")


def create_match(session: Session, user: User, data: MatchCreate) -> Match:
    ensure_club_access(session, user, data.club_id, write=True)
    ids = [data.team_a_id, data.team_b_id]
    validate_teams(session, data.club_id, ids, set(ids))
    match = Match(**data.model_dump(), created_by_user_id=user.id)
    session.add(match)
    return commit_record(
        session, match, "Match relationships changed; reload and try again"
    )


def update_match(
    session: Session, user: User, match_id: int, data: MatchUpdate
) -> Match:
    match = get_match(session, user, match_id)
    ensure_club_access(session, user, match.club_id, write=True)
    changes = data.model_dump(exclude_unset=True)
    a = changes.get("team_a_id", match.team_a_id)
    b = changes.get("team_b_id", match.team_b_id)
    changed_ids = {
        changes[key]
        for key in ("team_a_id", "team_b_id")
        if key in changes and changes[key] != getattr(match, key)
    }
    validate_teams(session, match.club_id, [a, b], changed_ids)
    length = changes.get("pitch_length_metres", match.pitch_length_metres)
    width = changes.get("pitch_width_metres", match.pitch_width_metres)
    if length < width:
        raise DomainError(422, "Pitch length must be at least its width")
    apply_changes(match, changes)
    return commit_record(
        session, match, "Match relationships changed; reload and try again"
    )
