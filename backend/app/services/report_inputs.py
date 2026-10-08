"""Read-only report dependencies, using the existing current-result guards."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import STAFF_ROLES, has_roles
from app.core.config import Settings
from app.models.media import MatchVideo
from app.models.user import User
from app.services import player_analytics_service as players
from app.services import team_analytics_service as tactics
from app.services.domain_common import DomainError
from app.services.match_service import get_match
from app.services.result_inputs import current_result
from app.services.team_assignment_service import assignment_query, tracking_version


@dataclass(frozen=True)
class ReportInputs:
    snapshot: dict
    metadata: dict
    video_id: int | None
    assignments: dict[int, str] | None
    players: players.AnalyticsSource | None
    tactics: tactics.TacticsSource | None
    unavailable: dict[str, str]


def reader_match(session: Session, user: User, match_id: int):
    if not user.is_active or not has_roles(user, STAFF_ROLES):
        raise DomainError(
            403, "Staff access is required for match reports and exports."
        )
    return get_match(session, user, match_id)


def _optional[T](
    load: Callable[[], T], name: str, unavailable: dict[str, str]
) -> T | None:
    try:
        return load()
    except DomainError as error:
        # Permission failures and unexpected errors must never become empty data.
        if error.status_code != 409:
            raise
        unavailable[name] = error.detail
        return None


def current_assignments(
    session: Session, match, settings: Settings
) -> tuple[dict[int, str], dict]:
    tracks = current_result(session, match, "tracking", settings)
    version = tracking_version(tracks.version)
    labels = {
        row.track_id: str(row.effective_team)
        for row in session.scalars(assignment_query(match.id, version))
    }
    if not labels and tracks.tracking.unique_tracks:
        raise DomainError(
            409,
            "Current team assignments are unavailable. Complete team classification.",
        )
    return labels, {
        "tracking_version": version,
        "effective_sha256": tracking_version({str(k): v for k, v in labels.items()}),
    }


def _result_version(source, field: str) -> dict | None:
    if source is None:
        return None
    return deepcopy(
        {
            "job_id": source.job.id,
            "attempt": source.job.attempt,
            "video_id": source.job.video_id,
            "trajectory_snapshot": source.job.trajectory_snapshot,
            "summary": getattr(source.job, field),
        }
    )


def capture_inputs(
    session: Session, user: User, match_id: int, settings: Settings
) -> ReportInputs:
    match = reader_match(session, user, match_id)
    metadata = {
        "match_id": match.id,
        "title": match.title,
        "club": match.club.name,
        "team_a": match.team_a.name,
        "team_b": match.team_b.name,
        "match_date": match.match_date.isoformat() if match.match_date else None,
        "match_format": match.match_format,
        "venue": match.venue,
        "pitch_length_metres": match.pitch_length_metres,
        "pitch_width_metres": match.pitch_width_metres,
    }
    video_id = session.scalar(
        select(MatchVideo.id).where(
            MatchVideo.match_id == match_id, MatchVideo.is_active.is_(True)
        )
    )
    unavailable: dict[str, str] = {}
    assignment_data = _optional(
        lambda: current_assignments(session, match, settings),
        "assignments",
        unavailable,
    )
    physical = _optional(
        lambda: players._current(session, user, match_id, settings),
        "players",
        unavailable,
    )
    tactical = _optional(
        lambda: tactics._current(session, user, match_id, settings),
        "tactics",
        unavailable,
    )
    snapshot = {
        "format": "match_report_v1",
        "metadata": metadata,
        "video_id": video_id,
        "assignments": assignment_data[1] if assignment_data else None,
        "players": _result_version(physical, "analytics_summary"),
        "tactics": _result_version(tactical, "tactics_summary"),
        "unavailable": unavailable,
        "heatmap_limit": settings.report_heatmap_limit,
    }
    return ReportInputs(
        snapshot,
        metadata,
        video_id,
        assignment_data[0] if assignment_data else None,
        physical,
        tactical,
        unavailable,
    )
