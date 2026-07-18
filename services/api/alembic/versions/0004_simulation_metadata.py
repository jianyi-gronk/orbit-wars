"""Add immutable simulation request metadata.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("matches")}
    if "map_id" not in columns:
        op.add_column(
            "matches",
            sa.Column(
                "map_id",
                sa.String(length=64),
                nullable=False,
                server_default="orbit-standard-v1",
            ),
        )
    if "request_key" not in columns:
        op.add_column("matches", sa.Column("request_key", sa.String(length=64)))
        op.create_index("ix_matches_request_key", "matches", ["request_key"], unique=True)
    if "request_hash" not in columns:
        op.add_column("matches", sa.Column("request_hash", sa.String(length=64)))


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("matches")}
    indexes = {index["name"] for index in sa.inspect(connection).get_indexes("matches")}
    if "request_hash" in columns:
        op.drop_column("matches", "request_hash")
    if "request_key" in columns:
        if "ix_matches_request_key" in indexes:
            op.drop_index("ix_matches_request_key", table_name="matches")
        op.drop_column("matches", "request_key")
    if "map_id" in columns:
        op.drop_column("matches", "map_id")
