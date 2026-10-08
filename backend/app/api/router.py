from fastapi import APIRouter, Depends, Response

from app.api.auth import router as auth_router
from app.api.calibration import router as calibration_router
from app.api.clubs import router as clubs_router
from app.api.coordinates import router as coordinates_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.matches import router as matches_router
from app.api.player_analytics import router as player_analytics_router
from app.api.players import router as players_router
from app.api.reports import router as reports_router
from app.api.review import router as review_router
from app.api.signup_requests import router as signup_requests_router
from app.api.team_analytics import router as team_analytics_router
from app.api.team_assignments import router as team_assignments_router
from app.api.team_colors import router as team_colors_router
from app.api.teams import router as teams_router
from app.api.trajectories import router as trajectories_router
from app.api.users import router as users_router
from app.api.videos import router as videos_router


def disable_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


api_router = APIRouter(dependencies=[Depends(disable_response_caching)])
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(signup_requests_router)
api_router.include_router(clubs_router)
api_router.include_router(teams_router)
api_router.include_router(players_router)
api_router.include_router(matches_router)
api_router.include_router(videos_router)
api_router.include_router(jobs_router)
api_router.include_router(calibration_router)
api_router.include_router(review_router)
api_router.include_router(team_assignments_router)
api_router.include_router(team_colors_router)
api_router.include_router(coordinates_router)
api_router.include_router(trajectories_router)
api_router.include_router(player_analytics_router)
api_router.include_router(team_analytics_router)
api_router.include_router(reports_router)
