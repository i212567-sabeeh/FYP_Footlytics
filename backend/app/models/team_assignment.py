"""One assignment per track and exact tracking version, never per video frame."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.football import Timestamps


class TrackTeamAssignment(Timestamps, Base):
    __tablename__ = "track_team_assignments"
    __table_args__ = (
        CheckConstraint(
            "classification_mode IN ('automatic', 'user_seeded')",
            name="classification_mode",
        ),
        ForeignKeyConstraint(
            ["match_id", "tracking_job_id"],
            ["processing_jobs.match_id", "processing_jobs.id"],
            name="fk_track_team_assignments_tracking_match",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("match_id", "tracking_version", "track_id"),
        CheckConstraint("track_id > 0", name="positive_track_id"),
        CheckConstraint(
            "automatic_team IN ('team_a', 'team_b', 'unknown')", name="automatic_team"
        ),
        CheckConstraint(
            "manual_team IS NULL OR manual_team IN ('team_a', 'team_b', 'unknown')",
            name="manual_team",
        ),
        CheckConstraint(
            "automatic_confidence >= 0 AND automatic_confidence <= 1",
            name="confidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="RESTRICT"))
    tracking_job_id: Mapped[int] = mapped_column(Integer, index=True)
    # Digest of existing video/calibration/detection/tracking provenance guards.
    tracking_version: Mapped[str] = mapped_column(String(64))
    track_id: Mapped[int] = mapped_column(Integer)
    automatic_team: Mapped[str] = mapped_column(String(10))
    automatic_confidence: Mapped[float] = mapped_column(Float)
    classification_mode: Mapped[str] = mapped_column(
        String(16), default="automatic", server_default="automatic"
    )
    classification_provenance: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True)
    )
    manual_team: Mapped[str | None] = mapped_column(String(10))
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    @property
    def effective_team(self) -> str:
        # Derived so clearing an override cannot leave a stale effective value.
        return self.manual_team if self.manual_team is not None else self.automatic_team
