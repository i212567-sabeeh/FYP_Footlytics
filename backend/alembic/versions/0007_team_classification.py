"""Track-level jersey assignments and classification job provenance.

Revision ID: 0007_team_classification
Revises: 0006_player_tracking
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_team_classification"
down_revision = "0006_player_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("processing_jobs") as batch:
        batch.create_unique_constraint(
            "uq_processing_jobs_match_id", ["match_id", "id"]
        )
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking', "
            "'team_classification')",
        )
        batch.add_column(sa.Column("tracking_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("classification_summary", sa.JSON(), nullable=True))
    op.create_table(
        "track_team_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.Column("tracking_job_id", sa.Integer(), nullable=False),
        sa.Column("tracking_version", sa.String(64), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("automatic_team", sa.String(10), nullable=False),
        sa.Column("automatic_confidence", sa.Float(), nullable=False),
        sa.Column("manual_team", sa.String(10), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["match_id", "tracking_job_id"],
            ["processing_jobs.match_id", "processing_jobs.id"],
            name="fk_track_team_assignments_tracking_match",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("match_id", "tracking_version", "track_id"),
        sa.CheckConstraint(
            "track_id > 0", name=op.f("ck_track_team_assignments_positive_track_id")
        ),
        sa.CheckConstraint(
            "automatic_team IN ('team_a', 'team_b', 'unknown')",
            name=op.f("ck_track_team_assignments_automatic_team"),
        ),
        sa.CheckConstraint(
            "manual_team IS NULL OR manual_team IN ('team_a', 'team_b', 'unknown')",
            name=op.f("ck_track_team_assignments_manual_team"),
        ),
        sa.CheckConstraint(
            "automatic_confidence >= 0 AND automatic_confidence <= 1",
            name=op.f("ck_track_team_assignments_confidence"),
        ),
    )
    op.create_index(
        "ix_track_team_assignments_tracking_job_id",
        "track_team_assignments",
        ["tracking_job_id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM processing_jobs "
            "WHERE job_type = 'team_classification'"
        )
    ) or op.get_bind().scalar(sa.text("SELECT count(*) FROM track_team_assignments")):
        raise RuntimeError("Cannot downgrade while team classification data exists.")
    op.drop_table("track_team_assignments")
    with op.batch_alter_table("processing_jobs") as batch:
        batch.drop_constraint("uq_processing_jobs_match_id", type_="unique")
        batch.drop_column("classification_summary")
        batch.drop_column("tracking_snapshot")
        batch.drop_constraint(op.f("ck_processing_jobs_job_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_processing_jobs_job_type"),
            "job_type IN ('video_preparation', 'player_detection', 'player_tracking')",
        )
