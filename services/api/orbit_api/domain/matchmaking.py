"""Unified controller-agnostic matchmaking and repeat-opponent controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import Fleet, Match, MatchMode, MatchParticipant, MatchStatus, Rating


class MatchmakingError(RuntimeError):
    code = "matchmaking.unavailable"


class ChallengeRestricted(MatchmakingError):
    code = "challenge.restricted"


@dataclass(frozen=True)
class MatchOffer:
    opponent: Fleet
    reason: str
    rating_difference: float
    recent_repeats: int
    rating_multiplier: float


def repeat_multiplier(recent_repeats: int) -> float:
    return (1.0, 0.5, 0.25, 0.0)[min(recent_repeats, 3)]


def _score(session: Session, fleet_id: Any) -> float:
    rating = session.get(Rating, fleet_id)
    return rating.display_score if rating else 0.0


def _recent_pair_counts(session: Session, fleet_id: Any) -> dict[Any, int]:
    cutoff = utc_now() - timedelta(hours=24)
    rows = session.execute(
        select(Match.id, MatchParticipant.fleet_id)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            Match.mode == MatchMode.RANKED,
            Match.status == MatchStatus.FINISHED,
            Match.created_at >= cutoff,
        )
    ).all()
    by_match: dict[Any, list[Any]] = {}
    for match_id, participant_fleet_id in rows:
        by_match.setdefault(match_id, []).append(participant_fleet_id)
    counts: dict[Any, int] = {}
    for participants in by_match.values():
        if fleet_id in participants and len(participants) == 2:
            opponent_id = participants[0] if participants[1] == fleet_id else participants[1]
            counts[opponent_id] = counts.get(opponent_id, 0) + 1
    return counts


class Matchmaker:
    def find(self, session: Session, fleet: Fleet, controller_type: str) -> MatchOffer:
        del controller_type  # Controller is an attribution label, never a separate pool.
        own_score = _score(session, fleet.id)
        repeats = _recent_pair_counts(session, fleet.id)
        candidates = list(session.scalars(select(Fleet).where(Fleet.id != fleet.id)))
        if not candidates:
            raise MatchmakingError("no public opponent is available")
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                abs(_score(session, candidate.id) - own_score) + repeats.get(candidate.id, 0) * 400,
                candidate.created_at,
            ),
        )
        opponent = ranked[0]
        difference = abs(_score(session, opponent.id) - own_score)
        repeated = repeats.get(opponent.id, 0)
        return MatchOffer(
            opponent,
            f"closest_rating;difference={difference:.1f};recent_repeats={repeated}",
            difference,
            repeated,
            repeat_multiplier(repeated),
        )

    def challenge(self, session: Session, fleet: Fleet, opponent: Fleet) -> MatchOffer:
        difference = abs(_score(session, fleet.id) - _score(session, opponent.id))
        repeated = _recent_pair_counts(session, fleet.id).get(opponent.id, 0)
        if difference > 800 or repeated >= 3:
            raise ChallengeRestricted("rating gap or repeated opponent limit was exceeded")
        return MatchOffer(
            opponent,
            f"direct_challenge;difference={difference:.1f};recent_repeats={repeated}",
            difference,
            repeated,
            repeat_multiplier(repeated),
        )
