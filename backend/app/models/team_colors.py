"""Versioned analyst-selected jersey examples; no images are stored in SQLite."""

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.football import Timestamps


class TeamColorSet(Timestamps, Base):
    __tablename__ = "team_color_sets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["match_id", "tracking_job_id"],
            ["processing_jobs.match_id", "processing_jobs.id"],
            name="fk_team_color_sets_tracking_match",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), index=True
    )
    video_id: Mapped[int] = mapped_column(
        ForeignKey("match_videos.id", ondelete="RESTRICT")
    )
    tracking_job_id: Mapped[int] = mapped_column(Integer)
    tracking_version: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    samples: Mapped[list] = mapped_column(JSON)
    prototypes: Mapped[list] = mapped_column(JSON)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
