"""Match-scoped calibration, with source and pitch-size provenance."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.club_access import ensure_club_access
from app.core.config import Settings
from app.cv.homography import (
    compute_homography,
    compute_reprojection_error,
    transform_points,
)
from app.database.base import utc_now
from app.models.calibration import PitchCalibration
from app.models.media import MatchVideo
from app.models.user import User
from app.schemas.calibration import CalibrationWrite
from app.services.domain_common import DomainError, commit_record
from app.services.frame_service import CalibrationFrame, extract_frame
from app.services.job_service import lock_match_for_media
from app.services.match_service import get_match
from app.services.upload_service import active_video

# Numerical round-off only: 0.1 mm in pitch space, never silently clamp points.
PITCH_TOLERANCE_METRES = 1e-4


def _source(session: Session, match_id: int) -> MatchVideo:
    video = active_video(session, match_id)
    if video is None:
        raise DomainError(409, "Upload a valid active match video before calibrating.")
    return video


def _record(session: Session, match_id: int, video_id: int) -> PitchCalibration | None:
    return session.scalar(
        select(PitchCalibration).where(
            PitchCalibration.match_id == match_id, PitchCalibration.video_id == video_id
        )
    )


def get_calibration(
    session: Session, user: User, match_id: int
) -> PitchCalibration | None:
    match = get_match(session, user, match_id)
    video = active_video(session, match_id)
    if video is None:
        return None
    calibration = _record(session, match_id, video.id)
    if calibration is not None and (
        calibration.pitch_length_metres != match.pitch_length_metres
        or calibration.pitch_width_metres != match.pitch_width_metres
    ):
        return None
    return calibration


def get_frame(
    session: Session,
    user: User,
    match_id: int,
    timestamp_seconds: float,
    settings: Settings,
) -> CalibrationFrame:
    get_match(session, user, match_id)
    video = _source(session, match_id)
    session.commit()  # Do not hold a read transaction during decoder I/O.
    frame = extract_frame(video, timestamp_seconds, settings)
    session.expire_all()
    get_match(session, user, match_id)
    if _source(session, match_id).id != frame.video_id:
        raise DomainError(
            409, "The source video changed. Request a new calibration frame."
        )
    return frame


def _check_bounds(
    points: list[tuple[float, float]],
    width: float,
    height: float,
    tolerance: float,
    label: str,
) -> None:
    if any(
        not (
            -tolerance <= x <= width + tolerance
            and -tolerance <= y <= height + tolerance
        )
        for x, y in points
    ):
        raise DomainError(
            422, f"{label} must lie within the source image or configured pitch bounds."
        )


def save_calibration(
    session: Session,
    user: User,
    match_id: int,
    data: CalibrationWrite,
    settings: Settings,
    *,
    replace: bool,
) -> PitchCalibration:
    match = get_match(session, user, match_id)
    ensure_club_access(session, user, match.club_id, write=True)
    if match.is_archived:
        raise DomainError(409, "Restore the match before changing its calibration.")
    video = _source(session, match_id)
    if video.id != data.video_id:
        raise DomainError(409, "Select a frame from the current active video.")
    calibration = _record(session, match_id, video.id)
    if calibration is not None and not replace:
        raise DomainError(
            409, "A calibration already exists for this video. Use PUT to replace it."
        )
    if calibration is None and replace:
        raise DomainError(404, "No calibration exists for the current video.")
    dimensions = (match.pitch_length_metres, match.pitch_width_metres)
    image = [(point.x, point.y) for point in data.image_points]
    pitch = [(point.x, point.y) for point in data.pitch_points]
    _check_bounds(pitch, *dimensions, PITCH_TOLERANCE_METRES, "Pitch points")
    session.commit()
    frame = extract_frame(video, data.source_timestamp_seconds, settings)
    _check_bounds(image, frame.width - 1, frame.height - 1, 1e-6, "Image points")
    try:
        matrix = compute_homography(image, pitch)
        projected = transform_points(image, matrix)
        error = compute_reprojection_error(image, pitch, matrix)
    except ValueError as exc:
        raise DomainError(422, str(exc)) from None
    _check_bounds(
        projected, *dimensions, PITCH_TOLERANCE_METRES, "Transformed calibration points"
    )

    # Share the Phase 4 lock with video replacement; recheck after slow decoding.
    match = lock_match_for_media(session, user, match_id)
    if _source(session, match_id).id != data.video_id or dimensions != (
        match.pitch_length_metres,
        match.pitch_width_metres,
    ):
        raise DomainError(
            409,
            "The source video or pitch dimensions changed. Reload before calibrating.",
        )
    calibration = _record(session, match_id, data.video_id)
    if (calibration is not None) != replace:
        raise DomainError(409, "The calibration changed. Reload before saving.")
    values = dict(
        source_frame_number=frame.frame_number,
        source_timestamp_seconds=frame.timestamp_seconds,
        image_width=frame.width,
        image_height=frame.height,
        pitch_length_metres=dimensions[0],
        pitch_width_metres=dimensions[1],
        image_points=[point.model_dump() for point in data.image_points],
        pitch_points=[point.model_dump() for point in data.pitch_points],
        homography_matrix=matrix.tolist(),
        reprojection_error=error,
    )
    if calibration is None:
        calibration = PitchCalibration(
            match_id=match_id,
            video_id=data.video_id,
            created_by_user_id=user.id,
            **values,
        )
        session.add(calibration)
    else:
        for key, value in values.items():
            setattr(calibration, key, value)
        calibration.updated_at = utc_now()
    return commit_record(
        session, calibration, "The calibration changed. Reload and try again."
    )
