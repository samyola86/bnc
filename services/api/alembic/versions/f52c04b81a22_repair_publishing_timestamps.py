"""Repair timestamp defaults missing from existing publishing request tables."""

import sqlalchemy as sa

from alembic import op

revision = "f52c04b81a22"
down_revision = "e41b02a77d31"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("publishing_requests") as batch:
        for name in ("created_at", "updated_at"):
            batch.alter_column(
                name,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=sa.func.now(),
            )


def downgrade():
    # These defaults are already required by the preceding revision and ORM.
    # Preserve them when reverting this repair.
    pass
