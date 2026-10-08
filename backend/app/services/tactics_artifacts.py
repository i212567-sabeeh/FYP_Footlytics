from app.schemas.team_analytics import TeamSnapshot, TeamTacticalSummary
from app.services.analytics_artifacts import AnalyticsArtifacts

MODELS = {
    "team_tactics_frames": TeamSnapshot,
    "team_tactics_summary": TeamTacticalSummary,
}


class TacticsArtifacts(AnalyticsArtifacts):
    models = MODELS
    prefix = "team_analytics"
