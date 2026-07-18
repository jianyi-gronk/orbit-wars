"""Create the phase-one persistence schema.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

from alembic import op
from orbit_api.db import models  # noqa: F401
from orbit_api.db.base import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the initial schema from the reviewed 0001 metadata snapshot."""
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    """Remove all objects introduced by the initial schema."""
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
