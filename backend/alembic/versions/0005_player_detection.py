"""Allow detection jobs and store small provenance/output metadata.

Revision ID: 0005_player_detection
Revises: 0004_pitch_calibration
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_player_detection"
down_revision = "0004_pitch_calibration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection')",
        )
        batch.add_column(sa.Column("calibration_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("detection_summary", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("artifact_relative_path", sa.String(500), nullable=True)
        )


def downgrade() -> None:
    # Earlier schemas cannot represent these jobs. Never silently delete history.
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs WHERE job_type = 'player_detection'"
        )
    ):
        raise RuntimeError("Cannot downgrade while player detection jobs exist.")
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_column("artifact_relative_path")
        batch.drop_column("detection_summary")
        batch.drop_column("calibration_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"), "job_type = 'video_preparation'"
        )
