from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.pagination import PaginationQuery
from app.auth.club_access import STAFF_ROLES, MatchEditor
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier, Page
from app.schemas.media import ProcessingJobRead
from app.services import job_service
from app.workers.queue import QueueDependency

router = APIRouter(tags=["processing jobs"])
JobReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@router.post(
    "/matches/{match_id}/jobs/video-preparation",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_preparation(
    match_id: Identifier,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_preparation(session, user, match_id, queue)


@router.post(
    "/matches/{match_id}/jobs/player-detection",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_detection(
    match_id: Identifier,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_detection(session, user, match_id, queue)


@router.post(
    "/matches/{match_id}/jobs/player-tracking",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_tracking(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_tracking(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/team-classification",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_classification(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_classification(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/coordinate-mapping",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_coordinate_mapping(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_coordinate_mapping(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/trajectory-cleaning",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_trajectory_cleaning(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_trajectory_cleaning(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/player-analytics",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_player_analytics(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_player_analytics(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/team-tactical-analytics",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_team_tactical_analytics(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_team_tactical_analytics(
        session, user, match_id, queue, request.app.state.settings
    )


@router.post(
    "/matches/{match_id}/jobs/match-report",
    response_model=ProcessingJobRead,
    status_code=202,
)
def create_match_report(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.create_match_report(
        session, user, match_id, queue, request.app.state.settings
    )


@router.get(
    "/matches/{match_id}/jobs/video-preparation",
    response_model=ProcessingJobRead | None,
)
def current_preparation(
    match_id: Identifier, session: DatabaseSession, user: JobReader
):
    return job_service.current_preparation(session, user, match_id)


@router.get("/matches/{match_id}/jobs", response_model=Page[ProcessingJobRead])
def list_jobs(
    match_id: Identifier,
    session: DatabaseSession,
    user: JobReader,
    page: PaginationQuery,
):
    return job_service.list_jobs(session, user, match_id, page.offset, page.limit)


@router.get("/jobs/{job_id}", response_model=ProcessingJobRead)
def get_job(job_id: Identifier, session: DatabaseSession, user: JobReader):
    return job_service.get_job(session, user, job_id)


@router.post("/jobs/{job_id}/retry", response_model=ProcessingJobRead, status_code=202)
def retry_job(
    job_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
    queue: QueueDependency,
):
    return job_service.retry_job(
        session, user, job_id, queue, request.app.state.settings
    )
