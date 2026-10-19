"""Persist revision-bound editorial publishing requests."""

import sqlalchemy as sa

from alembic import op

revision = "d23a10e93c41"
down_revision = "c71df24a6910"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publishing_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("story_id", sa.Uuid(), sa.ForeignKey("stories.id"), nullable=False),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("story_versions.id"), nullable=False),
        sa.Column("destinations", sa.JSON(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','SCHEDULED','CANCELLED')", name="ck_request_status"
        ),
    )
    op.create_index("ix_publishing_requests_story_id", "publishing_requests", ["story_id"])
    op.create_index("ix_publishing_requests_status", "publishing_requests", ["status"])


def downgrade():
    op.drop_table("publishing_requests")
