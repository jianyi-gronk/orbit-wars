"""Persist strategy draft simulation attribution.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("strategy_drafts")
    }
    if "validation_simulation_match_id" not in columns:
        with op.batch_alter_table("strategy_drafts") as batch:
            batch.add_column(sa.Column("validation_simulation_match_id", sa.Uuid()))
            batch.add_column(sa.Column("validation_simulation_revision", sa.Integer()))
            batch.create_foreign_key(
                "fk_strategy_drafts_validation_simulation_match_id_matches",
                "matches",
                ["validation_simulation_match_id"],
                ["id"],
            )


def downgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("strategy_drafts")
    }
    if "validation_simulation_match_id" in columns:
        with op.batch_alter_table("strategy_drafts") as batch:
            batch.drop_constraint(
                "fk_strategy_drafts_validation_simulation_match_id_matches",
                type_="foreignkey",
            )
            batch.drop_column("validation_simulation_revision")
            batch.drop_column("validation_simulation_match_id")
