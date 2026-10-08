"""Calibration prerequisites shared by queue creation, retry and the worker."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cv.homography import validate_homography
from app.models.calibration import PitchCalibration
from app.models.football import Match
from app.models.media import MatchVideo
from app.services.domain_common import DomainError


def current_calibration(
    session: Session, match: Match, video: MatchVideo
) -> PitchCalibration:
    calibration = session.scalar(
        select(PitchCalibration).where(
            PitchCalibration.match_id == match.id,
            PitchCalibration.video_id == video.id,
        )
    )
    if (
        calibration is None
        or not video.is_active
        or calibration.pitch_length_metres != match.pitch_length_metres
        or calibration.pitch_width_metres != match.pitch_width_metres
    ):
        raise DomainError(
            409,
            "Save a valid calibration for the active video and current pitch "
            "dimensions before detection.",
        )
    try:
        validate_homography(calibration.homography_matrix)
        if len(calibration.image_points) < 4 or len(calibration.image_points) != len(
            calibration.pitch_points
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise DomainError(
            409, "The saved calibration is invalid. Recalibrate before detection."
        ) from None
    return calibration


def snapshot(calibration: PitchCalibration) -> dict:
    return {
        "id": calibration.id,
        "updated_at": calibration.updated_at.isoformat(),
        "image_width": calibration.image_width,
        "image_height": calibration.image_height,
        "pitch_length_metres": calibration.pitch_length_metres,
        "pitch_width_metres": calibration.pitch_width_metres,
    }
