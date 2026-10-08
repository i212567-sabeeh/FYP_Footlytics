"""Import entities here so Alembic sees their shared metadata."""

from app.models.calibration import PitchCalibration
from app.models.football import (
    Club,
    ClubMembership,
    Match,
    Player,
    SquadMembership,
    Team,
)
from app.models.media import MatchVideo, ProcessingJob
from app.models.signup_request import SignupRequest
from app.models.team_assignment import TrackTeamAssignment
from app.models.team_colors import TeamColorSet
from app.models.user import Role, User, user_roles

__all__ = [
    "Role",
    "User",
    "user_roles",
    "Club",
    "ClubMembership",
    "Team",
    "Player",
    "SquadMembership",
    "Match",
    "MatchVideo",
    "ProcessingJob",
    "PitchCalibration",
    "TrackTeamAssignment",
    "SignupRequest",
    "TeamColorSet",
]
