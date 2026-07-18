"""Add strategy publication source and package size.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add metadata columns while supporting fresh databases from the 0001 snapshot."""
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("strategy_versions")}
    if "source" not in columns:
        op.add_column(
            "strategy_versions",
            sa.Column(
                "source",
                sa.String(length=255),
                nullable=False,
                server_default="unknown",
            ),
        )
        op.alter_column("strategy_versions", "source", server_default=None)
    if "package_size_bytes" not in columns:
        op.add_column(
            "strategy_versions",
            sa.Column(
                "package_size_bytes",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        op.alter_column("strategy_versions", "package_size_bytes", server_default=None)


def downgrade() -> None:
    """Remove metadata columns when they are present."""
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("strategy_versions")}
    if "package_size_bytes" in columns:
        op.drop_column("strategy_versions", "package_size_bytes")
    if "source" in columns:
        op.drop_column("strategy_versions", "source")
