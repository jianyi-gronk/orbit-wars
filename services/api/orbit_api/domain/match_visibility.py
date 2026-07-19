"""Shared classification for private candidate simulations."""

from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from orbit_api.db.models import MatchParticipant


def candidate_simulation_clause(match_id: Any) -> Any:
    """Return a correlated SQL clause for matches carrying candidate attribution."""

    return exists(
        select(MatchParticipant.id)
        .where(
            MatchParticipant.match_id == match_id,
            MatchParticipant.candidate_content_hash.is_not(None),
        )
        .correlate_except(MatchParticipant)
    )


def is_candidate_simulation(session: Session, match_id: UUID) -> bool:
    return bool(session.scalar(select(candidate_simulation_clause(match_id))))
