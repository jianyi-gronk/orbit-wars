"""Add transient candidate attribution to simulation participants.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(connection).get_columns("match_participants")
    }
    additions = {
        "candidate_content_hash": sa.Column("candidate_content_hash", sa.String(length=64)),
        "candidate_object_key": sa.Column("candidate_object_key", sa.String(length=512)),
        "candidate_manifest": sa.Column("candidate_manifest", sa.JSON()),
        "candidate_runtime_image": sa.Column("candidate_runtime_image", sa.String(length=255)),
        "candidate_submitted_by": sa.Column("candidate_submitted_by", sa.String(length=120)),
        "candidate_validation": sa.Column("candidate_validation", sa.JSON()),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("match_participants", column)


def downgrade() -> None:
    connection = op.get_bind()
    columns = {
        column["name"] for column in sa.inspect(connection).get_columns("match_participants")
    }
    for name in (
        "candidate_validation",
        "candidate_submitted_by",
        "candidate_runtime_image",
        "candidate_manifest",
        "candidate_object_key",
        "candidate_content_hash",
    ):
        if name in columns:
            op.drop_column("match_participants", name)
