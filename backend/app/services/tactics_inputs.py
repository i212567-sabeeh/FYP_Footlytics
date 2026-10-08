"""Exact trajectory and effective assignment inputs, independent of Phase 11."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.models.football import Match
from app.services.domain_common import DomainError
from app.services.result_inputs import current_result
from app.services.team_assignment_service import assignment_query, tracking_version
from app.services.trajectory_service import TrajectorySource, current_trajectories


@dataclass(frozen=True)
class TacticsInputs:
    trajectories: TrajectorySource
    assignments: dict[int, str]
    assignment_version: dict


def current_tactics_inputs(
    session: Session, match: Match, settings: Settings
) -> TacticsInputs:
    trajectories = current_trajectories(session, match, settings)
    tracks = current_result(session, match, "tracking", settings)
    version = tracking_version(tracks.version)
    assignments = {}
    count = 0
    for row in session.scalars(assignment_query(match.id, version)):
        count += 1
        if row.tracking_job_id != tracks.job.id or row.effective_team not in TrackTeam:
            raise DomainError(
                409, "Current team assignments are invalid. Classify teams again."
            )
        if row.effective_team != TrackTeam.UNKNOWN:
            assignments[row.track_id] = row.effective_team
    if not count and tracks.tracking.unique_tracks:
        raise DomainError(
            409, "No current team assignments. Run team classification first."
        )
    # Missing and explicit Unknown both contribute nothing. Only effective changes
    # matter: confidence edits or a masked automatic label do not stale the result.
    digest = tracking_version({str(k): v for k, v in assignments.items()})
    return TacticsInputs(
        trajectories,
        assignments,
        {"tracking_version": version, "effective_sha256": digest},
    )
