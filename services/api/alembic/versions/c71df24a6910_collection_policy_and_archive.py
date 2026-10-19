"""Global collection policy and non-destructive source archive."""

import sqlalchemy as sa

from alembic import op

revision = "c71df24a6910"
down_revision = "a81b6d2c930f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sources", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("sources", sa.Column("draft_language", sa.String(8)))
    op.add_column(
        "collection_runs",
        sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"),
    )
    with op.batch_alter_table("ingestion_settings") as batch:
        batch.add_column(
            sa.Column("default_interval", sa.Integer(), nullable=False, server_default="15")
        )
        batch.add_column(
            sa.Column("draft_language", sa.String(8), nullable=False, server_default="bn")
        )
        batch.add_column(
            sa.Column("source_mode", sa.String(24), nullable=False, server_default="all_supported")
        )
        batch.add_column(
            sa.Column("preferred_categories", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column(
                "automatic_collection", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
        batch.create_check_constraint("ck_default_interval", "default_interval BETWEEN 5 AND 1440")
        batch.create_check_constraint("ck_default_draft_language", "draft_language IN ('bn','en')")
        batch.create_check_constraint(
            "ck_source_mode", "source_mode IN ('all_supported','feeds_only')"
        )
    with op.batch_alter_table("ingestion_settings") as batch:
        for name in (
            "default_interval",
            "draft_language",
            "source_mode",
            "preferred_categories",
            "automatic_collection",
        ):
            batch.alter_column(name, server_default=None)
    with op.batch_alter_table("collection_runs") as batch:
        batch.alter_column("trigger", server_default=None)


def downgrade():
    with op.batch_alter_table("ingestion_settings") as batch:
        for name in ("ck_default_interval", "ck_default_draft_language", "ck_source_mode"):
            batch.drop_constraint(name, type_="check")
        for name in (
            "default_interval",
            "draft_language",
            "source_mode",
            "preferred_categories",
            "automatic_collection",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("collection_runs") as batch:
        batch.drop_column("trigger")
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("draft_language")
        batch.drop_column("archived_at")
