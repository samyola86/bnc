"""sources feeds candidates and attributed drafts"""

import sqlalchemy as sa

from alembic import op

revision = "5a4a4417e4ba"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingested_items",
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("editorial_status", sa.String(length=24), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("bangladesh_relevance", sa.Integer(), nullable=False),
        sa.Column("public_impact", sa.Integer(), nullable=False),
        sa.Column("corroboration", sa.Integer(), nullable=False),
        sa.Column("uniqueness", sa.Integer(), nullable=False),
        sa.Column("rank_override", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
            "editorial_status IN ('DISCOVERED','SELECTED','DRAFT','DISMISSED')",
            name="ck_candidate_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("bangladesh_relevance BETWEEN 0 AND 100", name="ck_rank_relevance"),
        sa.CheckConstraint("public_impact BETWEEN 0 AND 100", name="ck_rank_impact"),
        sa.CheckConstraint("corroboration BETWEEN 0 AND 100", name="ck_rank_corroboration"),
        sa.CheckConstraint("uniqueness BETWEEN 0 AND 100", name="ck_rank_uniqueness"),
        sa.CheckConstraint(
            "rank_override IS NULL OR rank_override BETWEEN 0 AND 100", name="ck_rank_override"
        ),
        sa.UniqueConstraint("content_hash"),
        sa.UniqueConstraint("normalized_url"),
    )
    op.create_index(
        op.f("ix_ingested_items_editorial_status"),
        "ingested_items",
        ["editorial_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingested_items_published_at"), "ingested_items", ["published_at"], unique=False
    )
    op.create_table(
        "ingestion_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_limit", sa.Integer(), nullable=False),
        sa.CheckConstraint("candidate_limit BETWEEN 20 AND 50", name="ck_candidate_limit"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("event_details", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "collection_runs",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("duplicates", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED')",
            name="ck_collection_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_collection_runs_source_id"), "collection_runs", ["source_id"], unique=False
    )
    op.create_index(op.f("ix_collection_runs_status"), "collection_runs", ["status"], unique=False)
    op.create_table(
        "feeds",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column("last_modified", sa.String(length=200), nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "url", name="uq_source_feed"),
    )
    op.create_index(op.f("ix_feeds_source_id"), "feeds", ["source_id"], unique=False)
    op.create_table(
        "feed_entries",
        sa.Column("feed_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("guid", sa.String(length=64), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("publisher_name", sa.String(length=200), nullable=False),
        sa.Column("rights_status", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["feed_id"],
            ["feeds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["ingested_items.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "guid", name="uq_feed_guid"),
    )
    op.create_index(op.f("ix_feed_entries_feed_id"), "feed_entries", ["feed_id"], unique=False)
    op.create_index(op.f("ix_feed_entries_item_id"), "feed_entries", ["item_id"], unique=False)
    op.create_table(
        "story_sources",
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("ingested_item_id", sa.Uuid(), nullable=True),
        sa.Column("publisher_name", sa.String(length=200), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=True),
        sa.Column("attribution_text", sa.Text(), nullable=False),
        sa.Column("is_original_reporting", sa.Boolean(), nullable=False),
        sa.Column("rights_status", sa.String(length=100), nullable=False),
        sa.Column("entry_method", sa.String(length=16), nullable=False),
        sa.Column("last_edited_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["ingested_item_id"],
            ["ingested_items.id"],
        ),
        sa.ForeignKeyConstraint(
            ["last_edited_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["story_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_story_sources_story_id"), "story_sources", ["story_id"], unique=False)
    op.create_index(
        op.f("ix_story_sources_version_id"), "story_sources", ["version_id"], unique=False
    )
    # Preserve existing registry records as inactive manual references until an
    # editor explicitly grants metadata collection permissions.
    additions = [
        ("source_type", sa.String(24), "'manual'"),
        ("url", sa.String(2048), "''"),
        ("category", sa.String(100), "''"),
        ("active", sa.Boolean(), "false"),
        ("extraction_mode", sa.String(24), "'reference_only'"),
        ("polling_interval", sa.Integer(), "15"),
        ("health", sa.String(24), "'UNTESTED'"),
        ("failure_count", sa.Integer(), "0"),
    ]
    for name, column_type, default in additions:
        op.add_column(
            "sources", sa.Column(name, column_type, nullable=False, server_default=sa.text(default))
        )
    for name, column_type in [
        ("feed_url", sa.String(2048)),
        ("last_checked", sa.DateTime(timezone=True)),
        ("last_success", sa.DateTime(timezone=True)),
        ("last_error", sa.Text()),
        ("next_collection_at", sa.DateTime(timezone=True)),
        ("collection_lock_id", sa.Uuid()),
        ("locked_until", sa.DateTime(timezone=True)),
    ]:
        op.add_column("sources", sa.Column(name, column_type, nullable=True))
    op.execute("UPDATE sources SET url = homepage, notes = COALESCE(notes, '')")
    with op.batch_alter_table("sources") as batch:
        for name, column_type, _ in additions:
            batch.alter_column(name, existing_type=column_type, server_default=None)
        batch.create_check_constraint("ck_source_frequency", "polling_interval BETWEEN 5 AND 1440")
        batch.create_check_constraint(
            "ck_source_type", "source_type IN ('rss','website','api','json_feed','manual')"
        )
        batch.create_check_constraint(
            "ck_source_extraction", "extraction_mode IN ('metadata','reference_only')"
        )
    op.create_index("ix_sources_next_collection_at", "sources", ["next_collection_at"])
    with op.batch_alter_table("stories") as batch:
        batch.add_column(sa.Column("origin_item_id", sa.Uuid(), nullable=True))
        batch.create_unique_constraint("uq_story_origin", ["origin_item_id"])
        batch.create_foreign_key(
            "fk_stories_origin_item", "ingested_items", ["origin_item_id"], ["id"]
        )
    op.bulk_insert(
        sa.table(
            "ingestion_settings",
            sa.column("id", sa.Integer()),
            sa.column("candidate_limit", sa.Integer()),
        ),
        [{"id": 1, "candidate_limit": 30}],
    )


def downgrade():
    op.drop_table("story_sources")
    with op.batch_alter_table("stories") as batch:
        batch.drop_constraint("fk_stories_origin_item", type_="foreignkey")
        batch.drop_constraint("uq_story_origin", type_="unique")
        batch.drop_column("origin_item_id")
    op.drop_index("ix_sources_next_collection_at", table_name="sources")
    with op.batch_alter_table("sources") as batch:
        for name in ["ck_source_frequency", "ck_source_type", "ck_source_extraction"]:
            batch.drop_constraint(name, type_="check")
        for name in [
            "locked_until",
            "collection_lock_id",
            "failure_count",
            "next_collection_at",
            "last_error",
            "last_success",
            "last_checked",
            "health",
            "polling_interval",
            "extraction_mode",
            "active",
            "category",
            "feed_url",
            "url",
            "source_type",
        ]:
            batch.drop_column(name)
    for name in [
        "feed_entries",
        "feeds",
        "collection_runs",
        "audit_events",
        "ingestion_settings",
        "ingested_items",
    ]:
        op.drop_table(name)
