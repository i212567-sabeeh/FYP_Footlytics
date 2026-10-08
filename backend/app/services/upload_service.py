"""Bounded upload staging and transactional publication of a match source."""

import hashlib
import logging
from dataclasses import asdict
from pathlib import PurePath
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access
from app.core.config import Settings
from app.database.base import utc_now
from app.models.media import MatchVideo, ProcessingJob
from app.models.user import User
from app.services.domain_common import DomainError
from app.services.job_service import lock_match_for_media
from app.services.match_service import get_match
from app.services.storage_service import StorageService
from app.services.video_inspection import inspect_video

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024
ALLOWED_MIME_TYPES = {"video/mp4", "video/quicktime", "application/octet-stream", ""}


def validate_upload_name(
    filename: str | None, content_type: str | None
) -> tuple[str, str]:
    """Display names never participate in disk paths; reject unsafe names early."""
    if (
        not filename
        or len(filename) > 255
        or any(char in filename for char in ("/", "\\", ":"))
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        raise DomainError(422, "Use a simple video filename without folder paths.")
    suffix = PurePath(filename).suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        raise DomainError(422, "Only MP4 and MOV video files are supported.")
    if (content_type or "").split(";", 1)[0].strip().lower() not in ALLOWED_MIME_TYPES:
        raise DomainError(422, "The upload must be an MP4 or MOV video.")
    return filename, suffix


def active_video(session: Session, match_id: int) -> MatchVideo | None:
    return session.scalar(
        select(MatchVideo).where(
            MatchVideo.match_id == match_id, MatchVideo.is_active.is_(True)
        )
    )


def get_video(session: Session, user: User, match_id: int) -> MatchVideo | None:
    get_match(session, user, match_id)
    return active_video(session, match_id)


def check_upload(
    session: Session, user: User, match_id: int, replace: bool
) -> int | None:
    match = get_match(session, user, match_id)
    ensure_club_access(session, user, match.club_id, write=True)
    if match.is_archived:
        raise DomainError(409, "Restore the match before changing its source video.")
    current = active_video(session, match_id)
    if current is not None and not replace:
        raise DomainError(
            409, "A source video already exists. Use Replace Video explicitly."
        )
    if current is None and replace:
        raise DomainError(404, "There is no source video to replace.")
    if (
        session.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.match_id == match_id,
                ProcessingJob.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        is not None
    ):
        raise DomainError(
            409, "Wait for the active preparation job before replacing the video."
        )
    return current.id if current else None


def receive_video(
    session: Session,
    user: User,
    match_id: int,
    source: BinaryIO,
    filename: str | None,
    content_type: str | None,
    settings: Settings,
    *,
    replace: bool,
    expected_video_id: int | None,
) -> MatchVideo:
    name, suffix = validate_upload_name(filename, content_type)
    storage = StorageService(settings)
    temporary = storage.create_temporary(match_id, suffix)
    final_path: str | None = None
    committed = False
    uploader_id = user.id
    # Do not hold a SQLite read transaction while receiving/inspecting a video.
    session.rollback()
    try:
        digest = hashlib.sha256()
        size = 0
        with temporary.open("wb") as output:
            while chunk := source.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_size:
                    raise DomainError(
                        413, "The video exceeds the configured upload size limit."
                    )
                output.write(chunk)
                digest.update(chunk)
        if not size:
            raise DomainError(422, "The uploaded video is empty.")
        metadata = inspect_video(temporary, settings)

        # Both replacement and job creation take this short database write lock.
        # Re-check access and the expected source after slow I/O, before publication.
        lock_match_for_media(session, user, match_id)
        current_id = check_upload(session, user, match_id, replace)
        if current_id != expected_video_id:
            raise DomainError(
                409, "The source video changed during upload. Reload and try again."
            )
        current = active_video(session, match_id)
        if current is not None and current.sha256 == digest.hexdigest():
            raise DomainError(409, "This is already the active source video.")
        stored_name, final_path = storage.finalize(temporary, match_id, suffix)
        if current is not None:
            current.is_active = False
            current.updated_at = utc_now()
            session.flush()  # Retire first, satisfying the active-video unique index.
        video = MatchVideo(
            match_id=match_id,
            original_filename=name,
            stored_filename=stored_name,
            relative_storage_path=final_path,
            file_size_bytes=size,
            mime_type="video/mp4" if suffix == ".mp4" else "video/quicktime",
            uploaded_by_user_id=uploader_id,
            sha256=digest.hexdigest(),
            **asdict(metadata),
        )
        session.add(video)
        session.commit()
        committed = True
        session.refresh(video)
        logger.info(
            "Video %s; match_id=%s video_id=%s bytes=%s",
            "replaced" if replace else "uploaded",
            match_id,
            video.id,
            size,
        )
        # Retired files remain protected history for their jobs. Future dependent
        # artifacts must reference video_id; a replacement is a distinct source.
        return video
    except DomainError:
        logger.info("Video upload rejected; match_id=%s", match_id)
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise DomainError(
            409, "The match video changed. Reload and try again."
        ) from None
    except (OSError, SQLAlchemyError):
        session.rollback()
        logger.exception("Video upload storage/database failure; match_id=%s", match_id)
        raise DomainError(
            500, "The video could not be saved. Try again later."
        ) from None
    finally:
        # Do not remove a published file if only the post-commit response failed.
        if final_path is not None and not committed:
            storage.delete(final_path)
        storage.discard_temporary(temporary)
