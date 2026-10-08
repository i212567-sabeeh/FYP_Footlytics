from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.auth.club_access import STAFF_ROLES
from app.auth.dependencies import require_roles
from app.database.dependencies import DatabaseSession
from app.models.user import User
from app.schemas.football import Identifier
from app.schemas.review import DetectionReviewSummary, TrackingReviewSummary
from app.services import review_service

router = APIRouter(prefix="/matches", tags=["computer vision review"])
ReviewReader = Annotated[User, Depends(require_roles(*STAFF_ROLES))]
REVIEW_HEADERS = ["X-Job-Id", "X-Job-Updated-At"]


@router.get("/{match_id}/detections/summary", response_model=DetectionReviewSummary)
def detection_summary(
    match_id: Identifier, request: Request, session: DatabaseSession, user: ReviewReader
):
    return review_service.get_summary(
        session, user, match_id, "detections", request.app.state.settings
    )


@router.get("/{match_id}/tracking/summary", response_model=TrackingReviewSummary)
def tracking_summary(
    match_id: Identifier, request: Request, session: DatabaseSession, user: ReviewReader
):
    return review_service.get_summary(
        session, user, match_id, "tracking", request.app.state.settings
    )


def _preview(
    kind: review_service.ReviewKind,
    match_id: int,
    request: Request,
    session: DatabaseSession,
    user: User,
    frame_number: int | None,
    job_id: int | None,
    job_updated_at: datetime | None,
) -> Response:
    frame, result_job_id, updated_at = review_service.get_preview(
        session,
        user,
        match_id,
        kind,
        request.app.state.settings,
        frame_number,
        job_id,
        job_updated_at,
    )
    return Response(
        frame.jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Video-Id": str(frame.video_id),
            "X-Frame-Number": str(frame.frame_number),
            "X-Frame-Timestamp-Seconds": str(frame.timestamp_seconds),
            "X-Frame-Width": str(frame.width),
            "X-Frame-Height": str(frame.height),
            "X-Job-Id": str(result_job_id),
            "X-Job-Updated-At": updated_at,
        },
    )


@router.get(
    "/{match_id}/detections/preview",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def detection_preview(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: ReviewReader,
    frame_number: Annotated[int | None, Query(ge=0)] = None,
    job_id: Annotated[int | None, Query(gt=0)] = None,
    job_updated_at: datetime | None = None,
):
    return _preview(
        "detections",
        match_id,
        request,
        session,
        user,
        frame_number,
        job_id,
        job_updated_at,
    )


@router.get(
    "/{match_id}/tracking/preview",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def tracking_preview(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: ReviewReader,
    frame_number: Annotated[int | None, Query(ge=0)] = None,
    job_id: Annotated[int | None, Query(gt=0)] = None,
    job_updated_at: datetime | None = None,
):
    return _preview(
        "tracking",
        match_id,
        request,
        session,
        user,
        frame_number,
        job_id,
        job_updated_at,
    )
