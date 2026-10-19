"""Individual accounts, task assignments and exact-revision review history."""

import sqlalchemy as sa

from alembic import op

revision = "e41b02a77d31"
down_revision = "d23a10e93c41"
branch_labels = None
depends_on = None


def records():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("username", sa.String(80)))
        batch.create_unique_constraint("users_username_key", ["username"])
        batch.add_column(sa.Column("password_hash", sa.Text()))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("last_login", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("mfa_secret", sa.Text()))
        batch.add_column(
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("mfa_last_step", sa.Integer(), nullable=False, server_default="-1")
        )
    # Historical shared identities retain their IDs and all foreign keys, without login privileges.
    op.execute("UPDATE users SET role='CONTENT_WRITER', active=false")
    with op.batch_alter_table("users") as batch:
        batch.create_check_constraint(
            "ck_user_role", "role IN ('SUPERADMIN','EDITOR','CONTENT_WRITER')"
        )
        batch.alter_column("mfa_enabled", server_default=None)
        batch.alter_column("mfa_last_step", server_default=None)
    op.create_table(
        "login_sessions",
        *records(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mfa_verified", sa.Boolean(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_table(
        "password_reset_tokens",
        *records(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_table(
        "auth_attempts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "newsroom_tasks",
        *records(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("creator_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("story_id", sa.Uuid(), sa.ForeignKey("stories.id")),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "status IN ('TO_DO','IN_PROGRESS','IN_REVIEW','COMPLETED')", name="ck_task_status"
        ),
        sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name="ck_task_priority"),
    )
    for key in ("assignee_id", "story_id"):
        op.create_index(f"ix_newsroom_tasks_{key}", "newsroom_tasks", [key])
    with op.batch_alter_table("publishing_requests") as batch:
        batch.drop_constraint("ck_request_status", type_="check")
        batch.create_check_constraint(
            "ck_request_status",
            "status IN ('QUEUED','SCHEDULED','CANCELLED','IN_REVIEW','CHANGES_REQUESTED',"
            "'APPROVED','READY','REJECTED','WITHDRAWN')",
        )
        batch.add_column(sa.Column("submitter_id", sa.Uuid()))
        batch.add_column(sa.Column("reviewer_id", sa.Uuid()))
        batch.add_column(sa.Column("decided_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("review_notes", sa.String(5000), nullable=False, server_default="")
        )
        batch.create_foreign_key("fk_request_submitter", "users", ["submitter_id"], ["id"])
        batch.create_foreign_key("fk_request_reviewer", "users", ["reviewer_id"], ["id"])
    with op.batch_alter_table("publishing_requests") as batch:
        batch.alter_column("review_notes", server_default=None)
    op.create_table(
        "review_decisions",
        *records(),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("publishing_requests.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("notes", sa.String(5000), nullable=False),
        sa.Column("self_approval_override", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_review_decisions_request_id", "review_decisions", ["request_id"])


def downgrade():
    op.drop_table("review_decisions")
    op.execute(
        "UPDATE publishing_requests SET status='CANCELLED' "
        "WHERE status NOT IN ('QUEUED','SCHEDULED','CANCELLED')"
    )
    with op.batch_alter_table("publishing_requests") as batch:
        batch.drop_constraint("fk_request_submitter", type_="foreignkey")
        batch.drop_constraint("fk_request_reviewer", type_="foreignkey")
        batch.drop_constraint("ck_request_status", type_="check")
        batch.create_check_constraint(
            "ck_request_status", "status IN ('QUEUED','SCHEDULED','CANCELLED')"
        )
        for name in ("submitter_id", "reviewer_id", "decided_at", "review_notes"):
            batch.drop_column(name)
    for table in ("newsroom_tasks", "auth_attempts", "password_reset_tokens", "login_sessions"):
        op.drop_table(table)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.drop_constraint("users_username_key", type_="unique")
        for name in (
            "username",
            "password_hash",
            "deleted_at",
            "last_login",
            "mfa_secret",
            "mfa_enabled",
            "mfa_last_step",
        ):
            batch.drop_column(name)
