"""Presentation data read from already published analytics; no metric calculations."""

from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.user import User
from app.schemas.player_analytics import TrackAnalytics, TrackHeatmapRead
from app.schemas.team_analytics import TeamTacticalSummary
from app.services import player_analytics_service as player_service
from app.services import team_analytics_service as team_service
from app.services.domain_common import DomainError
from app.services.report_inputs import ReportInputs


@dataclass(frozen=True)
class ReportData:
    metadata: dict
    generated_at: datetime
    assignments: dict[int, str] | None
    players: list[TrackAnalytics] | None
    teams: list[TeamTacticalSummary] | None
    heatmaps: list[TrackHeatmapRead]
    unavailable: dict[str, str]
    source_jobs: dict[str, int]
    sprint_threshold_mps: float | None
    sprint_min_duration_seconds: float | None
    heatmap_limit: int
    # From the saved analytics summary; 0 means every consecutive observation.
    speed_window_seconds: float | None = None


def read_players(inputs: ReportInputs) -> list[TrackAnalytics] | None:
    if inputs.players is None:
        return None
    with closing(player_service._rows(inputs.players, "players")) as rows:
        result = list(rows)
    ids = [row.track_id for row in result]
    if len(result) != inputs.players.summary.unique_tracks or ids != sorted(set(ids)):
        raise DomainError(
            409, "The player analytics summary is invalid or unavailable."
        )
    return result


def load_report_data(
    inputs: ReportInputs,
    generated_at: datetime,
    session: Session,
    user: User,
    settings: Settings,
    progress: Callable[[int, int], None],
) -> ReportData:
    players = read_players(inputs)
    teams = team_service._summaries(inputs.tactics) if inputs.tactics else None
    heatmaps = []
    # A bounded, deterministic selection by Track ID, never a performance ranking.
    selected = [row for row in players or [] if row.active_duration_seconds > 0][
        : settings.report_heatmap_limit
    ]
    for index, row in enumerate(selected, 1):
        heatmaps.append(
            player_service.get_heatmap(
                session, user, inputs.metadata["match_id"], row.track_id, settings
            )
        )
        progress(index, len(selected))
    summary = inputs.players.summary if inputs.players else None
    return ReportData(
        inputs.metadata,
        generated_at,
        inputs.assignments,
        players,
        teams,
        heatmaps,
        inputs.unavailable,
        {
            name: source.job.id
            for name, source in (
                ("Player analytics", inputs.players),
                ("Team tactics", inputs.tactics),
            )
            if source
        },
        summary.sprint_speed_threshold_mps if summary else None,
        summary.sprint_min_duration_seconds if summary else None,
        settings.report_heatmap_limit,
        summary.speed_window_seconds if summary else None,
    )
