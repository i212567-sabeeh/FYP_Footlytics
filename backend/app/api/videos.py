import logging

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.api.video_upload import parse_video_upload
from app.auth.club_access import MatchEditor
from app.auth.dependencies import CurrentUser
from app.database.dependencies import DatabaseSession
from app.schemas.football import Identifier
from app.schemas.media import MatchVideoRead
from app.services.domain_common import DomainError
from app.services.storage_service import StorageService
from app.services.upload_service import check_upload, get_video, receive_video

router = APIRouter(prefix="/matches", tags=["videos"])
logger = logging.getLogger(__name__)
UPLOAD_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary"}},
                }
            }
        },
    }
}


@router.get("/{match_id}/video", response_model=MatchVideoRead | None)
def video_information(
    match_id: Identifier, session: DatabaseSession, user: CurrentUser
):
    return get_video(session, user, match_id)


async def upload(
    request: Request,
    match_id: int,
    session: DatabaseSession,
    user: CurrentUser,
    replace: bool,
):
    expected = await run_in_threadpool(check_upload, session, user, match_id, replace)
    # End auth/precheck's read transaction before waiting for a potentially large body.
    await run_in_threadpool(session.commit)
    logger.info("Video upload started; match_id=%s replacement=%s", match_id, replace)
    try:
        async with parse_video_upload(request, request.app.state.settings) as file:
            return await run_in_threadpool(
                receive_video,
                session,
                user,
                match_id,
                file.file,
                file.filename,
                file.content_type,
                request.app.state.settings,
                replace=replace,
                expected_video_id=expected,
            )
    except DomainError:
        logger.info("Video upload validation failed; match_id=%s", match_id)
        raise
    except OSError:
        logger.exception("Video upload temporary storage failed; match_id=%s", match_id)
        raise DomainError(
            500, "Upload storage is unavailable. Try again later."
        ) from None


@router.post(
    "/{match_id}/video",
    response_model=MatchVideoRead,
    status_code=201,
    openapi_extra=UPLOAD_SCHEMA,
)
async def upload_video(
    request: Request, match_id: Identifier, session: DatabaseSession, user: MatchEditor
):
    return await upload(request, match_id, session, user, False)


@router.put(
    "/{match_id}/video", response_model=MatchVideoRead, openapi_extra=UPLOAD_SCHEMA
)
async def replace_video(
    request: Request, match_id: Identifier, session: DatabaseSession, user: MatchEditor
):
    return await upload(request, match_id, session, user, True)


@router.get("/{match_id}/video/file", response_class=FileResponse)
def video_file(
    request: Request, match_id: Identifier, session: DatabaseSession, user: CurrentUser
):
    video = get_video(session, user, match_id)
    if video is None:
        raise DomainError(404, "No match video has been uploaded.")
    path = StorageService(request.app.state.settings).resolve(
        video.relative_storage_path
    )
    if not path.is_file():
        raise DomainError(404, "The stored video is no longer available.")
    return FileResponse(
        path,
        media_type=video.mime_type,
        filename=video.original_filename,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
