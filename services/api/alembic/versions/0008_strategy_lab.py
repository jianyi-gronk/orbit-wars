"""Add private strategy drafts and AI credit ledger.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "strategy_drafts" not in tables:
        op.create_table(
            "strategy_drafts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("fleet_id", sa.Uuid(), sa.ForeignKey("fleets.id"), nullable=False),
            sa.Column(
                "base_strategy_version_id",
                sa.Uuid(),
                sa.ForeignKey("strategy_versions.id"),
            ),
            sa.Column("source_code", sa.Text(), nullable=False),
            sa.Column("mode", sa.String(length=16), nullable=False, server_default="guided"),
            sa.Column("parameters", sa.JSON(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_validation", sa.JSON()),
            sa.Column("validated_content_hash", sa.String(length=64)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("fleet_id"),
        )
        op.create_index("ix_strategy_drafts_fleet_id", "strategy_drafts", ["fleet_id"])
    if "ai_credit_accounts" not in tables:
        op.create_table(
            "ai_credit_accounts",
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
            sa.Column("remaining", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("granted", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ai_assist_requests" not in tables:
        op.create_table(
            "ai_assist_requests",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("public_id", sa.String(length=64), nullable=False, unique=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("fleet_id", sa.Uuid(), sa.ForeignKey("fleets.id"), nullable=False),
            sa.Column("draft_revision", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("cost", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="reserved"),
            sa.Column(
                "model",
                sa.String(length=80),
                nullable=False,
                server_default="deepseek-v4-flash",
            ),
            sa.Column("input_tokens", sa.Integer()),
            sa.Column("output_tokens", sa.Integer()),
            sa.Column("error_code", sa.String(length=120)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_ai_assist_requests_public_id", "ai_assist_requests", ["public_id"])
        op.create_index("ix_ai_assist_requests_user_id", "ai_assist_requests", ["user_id"])
        op.create_index("ix_ai_assist_requests_fleet_id", "ai_assist_requests", ["fleet_id"])
        op.create_index("ix_ai_assist_requests_status", "ai_assist_requests", ["status"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("ai_assist_requests", "ai_credit_accounts", "strategy_drafts"):
        if table in tables:
            op.drop_table(table)
