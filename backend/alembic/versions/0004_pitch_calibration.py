"""Store source-bound pitch calibration and its geometry provenance.

Revision ID: 0004_pitch_calibration
Revises: 0003_match_videos_processing_jobs
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_pitch_calibration"
down_revision = "0003_match_videos_processing_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pitch_calibrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("source_frame_number", sa.Integer(), nullable=False),
        sa.Column("source_timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("image_width", sa.Integer(), nullable=False),
        sa.Column("image_height", sa.Integer(), nullable=False),
        sa.Column("pitch_length_metres", sa.Float(), nullable=False),
        sa.Column("pitch_width_metres", sa.Float(), nullable=False),
        sa.Column("image_points", sa.JSON(), nullable=False),
        sa.Column("pitch_points", sa.JSON(), nullable=False),
        sa.Column("homography_matrix", sa.JSON(), nullable=False),
        sa.Column("reprojection_error", sa.Float(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
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
            "source_frame_number >= 0", name=op.f("ck_pitch_calibrations_frame_number")
        ),
        sa.CheckConstraint(
            "source_timestamp_seconds >= 0",
            name=op.f("ck_pitch_calibrations_timestamp"),
        ),
        sa.CheckConstraint(
            "image_width > 0 AND image_height > 0",
            name=op.f("ck_pitch_calibrations_dimensions"),
        ),
        sa.CheckConstraint(
            "reprojection_error >= 0",
            name=op.f("ck_pitch_calibrations_reprojection_error"),
        ),
        sa.CheckConstraint(
            "pitch_length_metres >= pitch_width_metres AND pitch_width_metres > 0",
            name=op.f("ck_pitch_calibrations_pitch_dimensions"),
        ),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["match_id", "video_id"],
            ["match_videos.match_id", "match_videos.id"],
            name="fk_pitch_calibrations_video_match",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "video_id"),
    )
    op.create_index(
        "ix_pitch_calibrations_match_id", "pitch_calibrations", ["match_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_pitch_calibrations_match_id", table_name="pitch_calibrations")
    op.drop_table("pitch_calibrations")
