"""Add auditable matchmaking reason and anti-abuse multiplier.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("matches")}
    if "matchmaking_reason" not in columns:
        op.add_column("matches", sa.Column("matchmaking_reason", sa.String(length=255)))
    if "rating_multiplier" not in columns:
        op.add_column(
            "matches",
            sa.Column("rating_multiplier", sa.Float(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("matches")}
    if "rating_multiplier" in columns:
        op.drop_column("matches", "rating_multiplier")
    if "matchmaking_reason" in columns:
        op.drop_column("matches", "matchmaking_reason")
