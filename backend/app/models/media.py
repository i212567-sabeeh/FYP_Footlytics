"""Source videos and durable processing state; large artifacts stay in storage."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UTCDateTime
from app.models.football import Match, Timestamps
from app.models.user import User


class MatchVideo(Timestamps, Base):
    __tablename__ = "match_videos"
    __table_args__ = (
        UniqueConstraint("match_id", "id"),
        UniqueConstraint("relative_storage_path"),
        CheckConstraint("file_size_bytes > 0", name="positive_file_size"),
        CheckConstraint("width > 0 AND height > 0", name="positive_dimensions"),
        CheckConstraint("fps > 0 AND fps <= 240", name="valid_fps"),
        CheckConstraint("duration_seconds > 0", name="positive_duration"),
        CheckConstraint(
            "frame_count IS NULL OR frame_count > 0", name="positive_frame_count"
        ),
        Index(
            "uq_match_videos_active",
            "match_id",
            unique=True,
            sqlite_where=text("is_active"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(80))
    relative_storage_path: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))
    container_format: Mapped[str | None] = mapped_column(String(200))
    codec: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float)
    frame_count: Mapped[int | None] = mapped_column(BigInteger)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    sha256: Mapped[str | None] = mapped_column(String(64))
    warning_message: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    match: Mapped[Match] = relationship()
    uploaded_by: Mapped[User] = relationship()


class ProcessingJob(Timestamps, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("match_id", "id"),
        ForeignKeyConstraint(
            ["match_id", "video_id"],
            ["match_videos.match_id", "match_videos.id"],
            name="fk_processing_jobs_video_match",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification', 'coordinate_mapping', 'trajectory_cleaning', "
            "'player_analytics', 'team_tactical_analytics', 'match_report')",
            name="job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', "
            "'completed_with_warnings', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="progress"
        ),
        CheckConstraint("retry_count >= 0 AND attempt >= 0", name="retry_count"),
        Index(
            "uq_processing_jobs_active",
            "match_id",
            "video_id",
            "job_type",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), index=True
    )
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32))
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    current_stage: Mapped[str] = mapped_column(String(100))
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    rq_job_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_message: Mapped[str | None] = mapped_column(Text)
    warning_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Every retry invalidates earlier queue deliveries, even for the same row ID.
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Small provenance/summary only. Detection rows remain in a protected CSV.
    calibration_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    detection_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    detection_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    tracking_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    tracking_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    team_color_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    classification_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    coordinate_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    coordinate_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    trajectory_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    trajectory_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    analytics_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    assignment_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    tactics_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    report_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    report_summary: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    artifact_relative_path: Mapped[str | None] = mapped_column(String(500))
    match: Mapped[Match] = relationship(foreign_keys=[match_id])
    video: Mapped[MatchVideo] = relationship(foreign_keys=[video_id])
    created_by: Mapped[User] = relationship()
