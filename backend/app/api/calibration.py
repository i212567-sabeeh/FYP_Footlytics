from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.auth.club_access import MatchEditor
from app.auth.dependencies import CurrentUser
from app.database.dependencies import DatabaseSession
from app.models.calibration import PitchCalibration
from app.schemas.calibration import CalibrationWrite, PitchCalibrationRead
from app.schemas.football import Identifier
from app.services import calibration_service

router = APIRouter(prefix="/matches", tags=["pitch calibration"])
FRAME_HEADERS = [
    "X-Video-Id",
    "X-Frame-Number",
    "X-Frame-Timestamp-Seconds",
    "X-Frame-Width",
    "X-Frame-Height",
]


@router.get(
    "/{match_id}/calibration/frame",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def calibration_frame(
    request: Request,
    match_id: Identifier,
    session: DatabaseSession,
    user: CurrentUser,
    timestamp_seconds: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 0,
) -> Response:
    frame = calibration_service.get_frame(
        session, user, match_id, timestamp_seconds, request.app.state.settings
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
        },
    )


@router.get("/{match_id}/calibration", response_model=PitchCalibrationRead | None)
def calibration_information(
    match_id: Identifier, session: DatabaseSession, user: CurrentUser
) -> PitchCalibration | None:
    return calibration_service.get_calibration(session, user, match_id)


@router.post(
    "/{match_id}/calibration", response_model=PitchCalibrationRead, status_code=201
)
def create_calibration(
    request: Request,
    match_id: Identifier,
    data: CalibrationWrite,
    session: DatabaseSession,
    user: MatchEditor,
) -> PitchCalibration:
    return calibration_service.save_calibration(
        session, user, match_id, data, request.app.state.settings, replace=False
    )


@router.put("/{match_id}/calibration", response_model=PitchCalibrationRead)
def update_calibration(
    request: Request,
    match_id: Identifier,
    data: CalibrationWrite,
    session: DatabaseSession,
    user: MatchEditor,
) -> PitchCalibration:
    return calibration_service.save_calibration(
        session, user, match_id, data, request.app.state.settings, replace=True
    )
