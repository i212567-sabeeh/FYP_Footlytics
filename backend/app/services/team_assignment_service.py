"""Scoped assignments for exactly one current tracking result."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import STAFF_ROLES, has_roles
from app.core.config import Settings
from app.core.teams import TrackTeam
from app.database.base import utc_now
from app.models.team_assignment import TrackTeamAssignment
from app.models.user import User
from app.schemas.team_assignment import TeamAssignmentRead
from app.services.domain_common import DomainError, page_results
from app.services.match_service import get_match
from app.services.result_inputs import current_result


def tracking_version(snapshot: dict) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def assignment_query(match_id: int, version: str):
    return select(TrackTeamAssignment).where(
        TrackTeamAssignment.match_id == match_id,
        TrackTeamAssignment.tracking_version == version,
    )


def list_assignments(
    session: Session,
    user: User,
    match_id: int,
    settings: Settings,
    offset: int,
    limit: int,
):
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(403, "Staff access is required for team assignments.")
    source = current_result(
        session, get_match(session, user, match_id), "tracking", settings
    )
    return page_results(
        session,
        assignment_query(match_id, tracking_version(source.version)).order_by(
            TrackTeamAssignment.track_id
        ),
        TeamAssignmentRead,
        offset,
        limit,
    )


def set_override(
    session: Session,
    user: User,
    match_id: int,
    track_id: int,
    team: TrackTeam | None,
    settings: Settings,
) -> TrackTeamAssignment:
    from app.services.job_service import lock_match_for_media

    match = lock_match_for_media(session, user, match_id)
    source = current_result(session, match, "tracking", settings)
    assignment = session.scalar(
        assignment_query(match_id, tracking_version(source.version)).where(
            TrackTeamAssignment.track_id == track_id
        )
    )
    if assignment is None:
        raise DomainError(
            404, "No current assignment for this track. Run team classification first."
        )
    assignment.manual_team = team
    assignment.updated_by_user_id = user.id
    assignment.updated_at = utc_now()
    session.commit()
    return assignment
