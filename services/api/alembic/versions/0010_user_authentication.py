"""Add first-party user authentication persistence.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "auth_credentials" not in existing:
        op.create_table(
            "auth_credentials",
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("email_normalized", sa.String(length=254), nullable=False),
            sa.Column("password_hash", sa.String(length=512), nullable=False),
            sa.Column("failed_attempts", sa.Integer(), nullable=False),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("user_id"),
        )
        op.create_index(
            "ix_auth_credentials_email_normalized",
            "auth_credentials",
            ["email_normalized"],
            unique=True,
        )

    if "auth_challenges" not in existing:
        op.create_table(
            "auth_challenges",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("email_normalized", sa.String(length=254), nullable=False),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("code_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("email_normalized", "purpose", "expires_at", "request_fingerprint"):
            op.create_index(f"ix_auth_challenges_{column}", "auth_challenges", [column])

    if "auth_sessions" not in existing:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index(
            "ix_auth_sessions_token_digest", "auth_sessions", ["token_digest"], unique=True
        )
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    if "oauth_identities" not in existing:
        op.create_table(
            "oauth_identities",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("provider_subject", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=True),
            sa.Column("display_name", sa.String(length=120), nullable=True),
            sa.Column("avatar_url", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "provider_subject"),
        )
        op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "oauth_identities",
        "auth_sessions",
        "auth_challenges",
        "auth_credentials",
    ):
        if table_name in existing:
            op.drop_table(table_name)
