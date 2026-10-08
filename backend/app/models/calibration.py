"""One calibration per source video; current visibility follows the active source."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.football import Timestamps


class PitchCalibration(Timestamps, Base):
    __tablename__ = "pitch_calibrations"
    __table_args__ = (
        UniqueConstraint("match_id", "video_id"),
        ForeignKeyConstraint(
            ["match_id", "video_id"],
            ["match_videos.match_id", "match_videos.id"],
            name="fk_pitch_calibrations_video_match",
            ondelete="RESTRICT",
        ),
        CheckConstraint("source_frame_number >= 0", name="frame_number"),
        CheckConstraint("source_timestamp_seconds >= 0", name="timestamp"),
        CheckConstraint("image_width > 0 AND image_height > 0", name="dimensions"),
        CheckConstraint("reprojection_error >= 0", name="reprojection_error"),
        CheckConstraint(
            "pitch_length_metres >= pitch_width_metres AND pitch_width_metres > 0",
            name="pitch_dimensions",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), index=True
    )
    video_id: Mapped[int] = mapped_column(Integer)
    source_frame_number: Mapped[int] = mapped_column(Integer)
    source_timestamp_seconds: Mapped[float] = mapped_column(Float)
    image_width: Mapped[int] = mapped_column(Integer)
    image_height: Mapped[int] = mapped_column(Integer)
    # Snapshot dimensions detect a stale calibration after a Match pitch-size edit.
    pitch_length_metres: Mapped[float] = mapped_column(Float)
    pitch_width_metres: Mapped[float] = mapped_column(Float)
    image_points: Mapped[list[dict[str, float]]] = mapped_column(JSON)
    pitch_points: Mapped[list[dict[str, float]]] = mapped_column(JSON)
    homography_matrix: Mapped[list[list[float]]] = mapped_column(JSON)
    reprojection_error: Mapped[float] = mapped_column(Float)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
