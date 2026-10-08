"""Scoped, versioned jersey examples measured from bounded protected frame reads."""

import base64
from uuid import uuid4

import cv2
import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.teams import TrackTeam
from app.cv.team_classifier import jersey_crop, jersey_feature
from app.cv.team_colors import fit_prototype, validate_prototypes
from app.models.team_colors import TeamColorSet
from app.models.user import User
from app.schemas.team_colors import (
    ColorPreviewRead,
    TeamColorSetRead,
    TeamColorsRead,
    TeamColorsSave,
)
from app.services.domain_common import DomainError
from app.services.frame_service import extract_frame
from app.services.result_inputs import ResultSource, current_result
from app.services.review_service import _observations, _source
from app.services.team_assignment_service import tracking_version


def current_color_set(
    session: Session, match_id: int, version: dict
) -> TeamColorSet | None:
    return session.scalar(
        select(TeamColorSet)
        .where(
            TeamColorSet.match_id == match_id,
            TeamColorSet.tracking_version == tracking_version(version),
            TeamColorSet.is_active.is_(True),
        )
        .order_by(TeamColorSet.id.desc())
    )


def color_snapshot(session: Session, match_id: int, version: dict) -> dict | None:
    row = current_color_set(session, match_id, version)
    if row is None:
        return None
    return {
        "id": row.id,
        "tracking_version": row.tracking_version,
        "prototypes": row.prototypes,
    }


def get_colors(
    session: Session, user: User, match_id: int, settings: Settings
) -> TeamColorsRead:
    source = _source(session, user, match_id, "tracking", settings)
    row = current_color_set(session, match_id, source.version)
    return TeamColorsRead(
        tracking_job_id=source.job.id,
        tracking_version=tracking_version(source.version),
        current=TeamColorSetRead.model_validate(row) if row else None,
    )


def _measure(
    source: ResultSource, track_id: int, frame_number: int, settings: Settings
):
    number, boxes = _observations(
        source, frame_number, settings.video_inspection_timeout_seconds
    )
    selected = next((box for box in boxes if box.track_id == track_id), None)
    if selected is None:
        raise DomainError(404, "This track has no observation in the selected frame.")
    frame = extract_frame(source.video, 0, settings, frame_number=number)
    image = cv2.imdecode(np.frombuffer(frame.jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape != (
        source.detection.frame_height,
        source.detection.frame_width,
        3,
    ):
        raise DomainError(
            422, "The selected frame could not be decoded at the expected dimensions."
        )
    crop = jersey_crop(image, selected.bbox, settings)
    feature = jersey_feature(crop)
    if crop is None or feature is None:
        raise DomainError(
            422,
            "The torso crop is too small, outside the frame or unreadable. "
            "Choose another observation.",
        )
    return crop, feature


def preview_color(
    session: Session,
    user: User,
    match_id: int,
    track_id: int,
    frame_number: int,
    version: str,
    settings: Settings,
) -> ColorPreviewRead:
    source = _source(session, user, match_id, "tracking", settings)
    if tracking_version(source.version) != version:
        raise DomainError(409, "Tracking changed. Refresh team-color setup.")
    session.commit()
    crop, appearance = _measure(source, track_id, frame_number, settings)
    ok, encoded = cv2.imencode(".jpg", crop)
    if not ok:
        raise DomainError(422, "The crop preview could not be encoded.")
    session.rollback()
    if _source(session, user, match_id, "tracking", settings).version != source.version:
        raise DomainError(
            409, "Tracking changed during crop review. Refresh team-color setup."
        )
    usable = appearance.quality >= settings.team_unknown_threshold
    return ColorPreviewRead(
        track_id=track_id,
        frame_number=frame_number,
        tracking_version=version,
        crop_data_url="data:image/jpeg;base64,"
        + base64.b64encode(encoded).decode("ascii"),
        quality=appearance.quality,
        usable=usable,
        rejection_reason=None
        if usable
        else "Weak or background-heavy color evidence. Choose a clearer torso crop.",
    )


def save_colors(
    session: Session,
    user: User,
    match_id: int,
    data: TeamColorsSave,
    settings: Settings,
) -> TeamColorsRead:
    from app.services.job_service import lock_match_for_media

    match = lock_match_for_media(session, user, match_id)
    source = current_result(session, match, "tracking", settings)
    if tracking_version(source.version) != data.tracking_version:
        raise DomainError(409, "Tracking changed. Refresh team-color setup.")
    session.commit()  # Do not retain the match lock during bounded frame decoding.
    samples = []
    evidence = {team: [] for team in (TrackTeam.TEAM_A, TrackTeam.TEAM_B)}
    for selected in data.samples:
        _, feature = _measure(
            source, selected.track_id, selected.frame_number, settings
        )
        evidence[TrackTeam(selected.team)].append(feature)
        samples.append(
            {
                **selected.model_dump(),
                "id": uuid4().hex,
                "color": list(feature.color),
                "quality": feature.quality,
            }
        )
    try:
        prototypes = {
            team: fit_prototype(values, settings) for team, values in evidence.items()
        }
        validate_prototypes(prototypes)
    except ValueError as error:
        raise DomainError(422, str(error)) from None
    match = lock_match_for_media(session, user, match_id)
    current = current_result(session, match, "tracking", settings)
    if current.version != source.version:
        raise DomainError(
            409,
            "Tracking or video changed while measuring examples. "
            "Refresh team-color setup.",
        )
    session.execute(
        update(TeamColorSet)
        .where(TeamColorSet.match_id == match_id, TeamColorSet.is_active.is_(True))
        .values(is_active=False)
    )
    row = TeamColorSet(
        match_id=match_id,
        video_id=source.video.id,
        tracking_job_id=source.job.id,
        tracking_version=data.tracking_version,
        samples=samples,
        prototypes=[
            {
                "team": str(team),
                "color": list(value.color),
                "quality": value.quality,
                "sample_ids": [s["id"] for s in samples if s["team"] == team],
            }
            for team, value in prototypes.items()
        ],
        created_by_user_id=user.id,
    )
    session.add(row)
    session.commit()
    return get_colors(session, user, match_id, settings)


def clear_colors(
    session: Session, user: User, match_id: int, settings: Settings
) -> None:
    from app.services.job_service import lock_match_for_media

    lock_match_for_media(session, user, match_id)
    session.execute(
        update(TeamColorSet)
        .where(TeamColorSet.match_id == match_id, TeamColorSet.is_active.is_(True))
        .values(is_active=False)
    )
    session.commit()
