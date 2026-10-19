"""Persist evidence-bound AI draft jobs alongside shared story revisions."""

import sqlalchemy as sa

from alembic import op

revision = "a81b6d2c930f"
down_revision = "5a4a4417e4ba"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("story_id", sa.Uuid(), sa.ForeignKey("stories.id"), nullable=False),
        sa.Column("editor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("template_version", sa.String(50), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')", name="ck_ai_status"
        ),
    )
    for column in ("story_id", "editor_id", "status"):
        op.create_index(f"ix_ai_jobs_{column}", "ai_jobs", [column])


def downgrade():
    op.drop_table("ai_jobs")
