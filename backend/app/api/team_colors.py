from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.team_assignments import AssignmentReader
from app.auth.club_access import MatchEditor
from app.database.dependencies import DatabaseSession
from app.schemas.football import Identifier
from app.schemas.team_colors import ColorPreviewRead, TeamColorsRead, TeamColorsSave
from app.services import team_color_service as service

router = APIRouter(prefix="/matches/{match_id}/team-colors", tags=["team colors"])


@router.get("", response_model=TeamColorsRead)
def get_colors(
    match_id: Identifier,
    request: Request,
    session: DatabaseSession,
    user: AssignmentReader,
):
    return service.get_colors(session, user, match_id, request.app.state.settings)


@router.get("/preview", response_model=ColorPreviewRead)
def preview(
    match_id: Identifier,
    track_id: Identifier,
    frame_number: Annotated[int, Query(ge=0)],
    tracking_version: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
    request: Request,
    session: DatabaseSession,
    user: AssignmentReader,
):
    return service.preview_color(
        session,
        user,
        match_id,
        track_id,
        frame_number,
        tracking_version,
        request.app.state.settings,
    )


@router.put("", response_model=TeamColorsRead)
def save(
    match_id: Identifier,
    data: TeamColorsSave,
    request: Request,
    session: DatabaseSession,
    user: MatchEditor,
):
    return service.save_colors(
        session, user, match_id, data, request.app.state.settings
    )


@router.delete("", status_code=204)
def clear(
    match_id: Identifier, request: Request, session: DatabaseSession, user: MatchEditor
):
    service.clear_colors(session, user, match_id, request.app.state.settings)
    return Response(status_code=204)
