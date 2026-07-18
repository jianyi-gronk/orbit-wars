"""Add public replay metadata and analysis.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("replay_artifacts")}
    additions = (
        ("metadata_payload", sa.JSON(), None),
        ("analysis_payload", sa.JSON(), None),
        ("size_bytes", sa.BigInteger(), "0"),
        ("frame_count", sa.Integer(), "0"),
    )
    for name, kind, default in additions:
        if name not in columns:
            op.add_column(
                "replay_artifacts",
                sa.Column(name, kind, nullable=default is None, server_default=default),
            )


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("replay_artifacts")}
    for name in ("frame_count", "size_bytes", "analysis_payload", "metadata_payload"):
        if name in columns:
            op.drop_column("replay_artifacts", name)
