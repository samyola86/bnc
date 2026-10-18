"""Initial editorial foundation. Keep this migration independent of live models."""

import sqlalchemy as sa

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def record_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "users",
        *record_columns(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "sources",
        *record_columns(),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("homepage", sa.String(2048), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("rights", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text()),
    )
    op.create_table(
        "stories",
        *record_columns(),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.CheckConstraint("language IN ('bn', 'en')", name="ck_story_language"),
        sa.CheckConstraint(
            "status IN ('DISCOVERED','SELECTED','DRAFT','IN_REVIEW','CHANGES_REQUESTED',"
            "'APPROVED','READY','UPDATED','CORRECTED','RETRACTED')",
            name="ck_story_status",
        ),
    )
    op.create_index("ix_stories_status", "stories", ["status"])
    op.create_table(
        "story_versions",
        *record_columns(),
        sa.Column("story_id", sa.Uuid(), sa.ForeignKey("stories.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("editor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("story_id", "version_number", name="uq_story_revision"),
        sa.CheckConstraint("version_number > 0", name="ck_positive_revision"),
    )
    op.create_index("ix_story_versions_story_id", "story_versions", ["story_id"])
    op.create_table(
        "channels",
        *record_columns(),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("remote_account_id", sa.String(200)),
        sa.Column("encrypted_secret_reference", sa.String(500)),
    )
    op.create_table(
        "publications",
        *record_columns(),
        sa.Column(
            "approved_version_id", sa.Uuid(), sa.ForeignKey("story_versions.id"), nullable=False
        ),
        sa.Column("channel_id", sa.Uuid(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("remote_id", sa.String(200)),
        sa.Column("permalink", sa.String(2048)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING','SCHEDULED','RUNNING','CONFIRMED','RETRYABLE_FAILED',"
            "'PERMANENT_FAILED','UNKNOWN_RECONCILE','CANCELLED')",
            name="ck_publication_status",
        ),
    )
    op.create_index("ix_publications_channel_id", "publications", ["channel_id"])
    op.create_index("ix_publications_status", "publications", ["status"])


def downgrade():
    for table in ("publications", "channels", "story_versions", "stories", "sources", "users"):
        op.drop_table(table)
