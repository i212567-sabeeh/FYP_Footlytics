"""match_videos_processing_jobs

Revision ID: 0003_match_videos_processing_jobs
Revises: 0002_clubs_teams_players_matches
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_match_videos_processing_jobs"
down_revision: str | Sequence[str] | None = "0002_clubs_teams_players_matches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=80), nullable=False),
        sa.Column("relative_storage_path", sa.String(length=500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("container_format", sa.String(length=200), nullable=True),
        sa.Column("codec", sa.String(length=100), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.BigInteger(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("warning_message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_seconds > 0", name=op.f("ck_match_videos_positive_duration")
        ),
        sa.CheckConstraint(
            "file_size_bytes > 0", name=op.f("ck_match_videos_positive_file_size")
        ),
        sa.CheckConstraint(
            "fps > 0 AND fps <= 240", name=op.f("ck_match_videos_valid_fps")
        ),
        sa.CheckConstraint(
            "frame_count IS NULL OR frame_count > 0",
            name=op.f("ck_match_videos_positive_frame_count"),
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0", name=op.f("ck_match_videos_positive_dimensions")
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_videos_match_id_matches"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name=op.f("fk_match_videos_uploaded_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_videos")),
        sa.UniqueConstraint("match_id", "id", name=op.f("uq_match_videos_match_id")),
        sa.UniqueConstraint(
            "relative_storage_path", name=op.f("uq_match_videos_relative_storage_path")
        ),
    )
    with op.batch_alter_table("match_videos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_match_videos_match_id"), ["match_id"], unique=False
        )
        batch_op.create_index(
            "uq_match_videos_active",
            ["match_id"],
            unique=True,
            sqlite_where=sa.text("is_active"),
            postgresql_where=sa.text("is_active"),
        )

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_stage", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("rq_job_id", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warning_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_type = 'video_preparation'", name=op.f("ck_processing_jobs_job_type")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', "
            "'completed_with_warnings', 'failed', 'cancelled')",
            name=op.f("ck_processing_jobs_status"),
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name=op.f("ck_processing_jobs_progress"),
        ),
        sa.CheckConstraint(
            "retry_count >= 0 AND attempt >= 0",
            name=op.f("ck_processing_jobs_retry_count"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_processing_jobs_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_id", "video_id"],
            ["match_videos.match_id", "match_videos.id"],
            name="fk_processing_jobs_video_match",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_processing_jobs_match_id_matches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint("rq_job_id", name=op.f("uq_processing_jobs_rq_job_id")),
    )
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_processing_jobs_match_id"), ["match_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_processing_jobs_video_id"), ["video_id"], unique=False
        )
        batch_op.create_index(
            "uq_processing_jobs_active",
            ["match_id", "video_id", "job_type"],
            unique=True,
            sqlite_where=sa.text("status IN ('queued', 'running')"),
            postgresql_where=sa.text("status IN ('queued', 'running')"),
        )


def downgrade() -> None:
    with op.batch_alter_table("processing_jobs", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_processing_jobs_active",
            sqlite_where=sa.text("status IN ('queued', 'running')"),
            postgresql_where=sa.text("status IN ('queued', 'running')"),
        )
        batch_op.drop_index(batch_op.f("ix_processing_jobs_video_id"))
        batch_op.drop_index(batch_op.f("ix_processing_jobs_match_id"))

    op.drop_table("processing_jobs")
    with op.batch_alter_table("match_videos", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_match_videos_active",
            sqlite_where=sa.text("is_active"),
            postgresql_where=sa.text("is_active"),
        )
        batch_op.drop_index(batch_op.f("ix_match_videos_match_id"))

    op.drop_table("match_videos")
