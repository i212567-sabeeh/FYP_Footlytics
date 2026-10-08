from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from app.api.jobs import JobReader
from app.database.dependencies import DatabaseSession
from app.schemas.football import Identifier
from app.schemas.reports import ReportStatus
from app.services import report_service

router = APIRouter(prefix="/matches/{match_id}", tags=["reports and exports"])
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


@router.get("/report", response_model=ReportStatus)
def report_status(
    match_id: Identifier, request: Request, session: DatabaseSession, user: JobReader
):
    return report_service.report_status(
        session, user, match_id, request.app.state.settings
    )


@router.get("/report/file")
def report_file(
    match_id: Identifier, request: Request, session: DatabaseSession, user: JobReader
):
    path = report_service.report_file(
        session, user, match_id, request.app.state.settings
    )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"footlytics-match-{match_id}-report.pdf",
        headers=HEADERS,
    )


def _csv(
    match_id: int,
    request: Request,
    session: DatabaseSession,
    user: JobReader,
    family: str,
    filename: str,
):
    content = report_service.export_csv(
        session, user, match_id, request.app.state.settings, family
    )
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv",
        headers={
            **HEADERS,
            "Content-Disposition": (
                f'attachment; filename="footlytics-match-{match_id}-{filename}.csv"'
            ),
        },
    )


@router.get("/exports/player-analytics.csv")
def player_csv(
    match_id: Identifier, request: Request, session: DatabaseSession, user: JobReader
):
    return _csv(match_id, request, session, user, "players", "player-analytics")


@router.get("/exports/team-analytics.csv")
def team_csv(
    match_id: Identifier, request: Request, session: DatabaseSession, user: JobReader
):
    return _csv(match_id, request, session, user, "teams", "team-analytics")
