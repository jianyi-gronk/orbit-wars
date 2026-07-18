"""Add strategy validation report fields.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("strategy_versions")}
    if "validation_report" not in columns:
        op.add_column("strategy_versions", sa.Column("validation_report", sa.JSON(), nullable=True))
    if "validated_at" not in columns:
        op.add_column(
            "strategy_versions",
            sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("strategy_versions")}
    if "validated_at" in columns:
        op.drop_column("strategy_versions", "validated_at")
    if "validation_report" in columns:
        op.drop_column("strategy_versions", "validation_report")
