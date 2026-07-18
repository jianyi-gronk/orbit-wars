"""Single fleet rating identity with exactly-once match settlement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import (
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    Rating,
    RatingEvent,
)

DEFAULT_MU = 25.0
DEFAULT_SIGMA = 25.0 / 3.0
MIN_SIGMA = 2.5
RANK_BAND_SIZE = 100
MASTER_SCORE = 1500


class CompetitiveTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"
    MASTER = "master"


@dataclass(frozen=True, slots=True)
class CompetitiveRank:
    tier: CompetitiveTier
    division: str | None
    points: float

    def as_json(self) -> dict[str, str | float | None]:
        return {
            "tier": self.tier.value,
            "division": self.division,
            "points": self.points,
        }


class RatingError(RuntimeError):
    code = "rating.not_scoreable"


@dataclass(frozen=True)
class RatingDelta:
    fleet_id: Any
    before_mu: float
    before_sigma: float
    after_mu: float
    after_sigma: float
    before_score: float
    after_score: float

    def as_json(self, fleet: Fleet) -> dict[str, Any]:
        return {
            "fleetPublicId": fleet.public_id,
            "before": {
                "mu": self.before_mu,
                "sigma": self.before_sigma,
                "displayScore": self.before_score,
            },
            "after": {
                "mu": self.after_mu,
                "sigma": self.after_sigma,
                "displayScore": self.after_score,
            },
            "delta": self.after_score - self.before_score,
        }


def display_score(mu: float, sigma: float) -> float:
    return round(max(0.0, mu - 3 * sigma) * 100, 1)


def tier_for(score: float) -> str:
    if score >= 1800:
        return "Eclipse"
    if score >= 1200:
        return "Nova"
    if score >= 700:
        return "Vector"
    if score >= 300:
        return "Orbit"
    return "Cadet"


def competitive_rank_for(score: float) -> CompetitiveRank:
    """Map one unified score to a localized-client-friendly rank division."""
    normalized = max(0.0, score)
    if normalized >= MASTER_SCORE:
        return CompetitiveRank(
            CompetitiveTier.MASTER,
            None,
            round(normalized - MASTER_SCORE, 1),
        )

    tiers = (
        CompetitiveTier.BRONZE,
        CompetitiveTier.SILVER,
        CompetitiveTier.GOLD,
        CompetitiveTier.PLATINUM,
        CompetitiveTier.DIAMOND,
    )
    tier_index = min(int(normalized // (RANK_BAND_SIZE * 3)), len(tiers) - 1)
    tier_points = normalized - tier_index * RANK_BAND_SIZE * 3
    division_index = min(int(tier_points // RANK_BAND_SIZE), 2)
    divisions = ("III", "II", "I")
    return CompetitiveRank(
        tiers[tier_index],
        divisions[division_index],
        round(tier_points - division_index * RANK_BAND_SIZE, 1),
    )


class RatingService:
    def preview(
        self,
        ratings: tuple[Rating, Rating],
        winner_slot: int,
        *,
        multiplier: float = 1.0,
    ) -> tuple[RatingDelta, RatingDelta]:
        if winner_slot not in (0, 1):
            raise RatingError("a unique attributed winner is required")
        expected_zero = 1 / (1 + math.exp((ratings[1].mu - ratings[0].mu) / 8))
        outcomes = (1.0 if winner_slot == 0 else 0.0, 1.0 if winner_slot == 1 else 0.0)
        expected = (expected_zero, 1 - expected_zero)
        uncertainty = min(1.0, (ratings[0].sigma + ratings[1].sigma) / (2 * DEFAULT_SIGMA))
        movement = 4.0 * uncertainty * max(0.0, min(1.0, multiplier))
        deltas: list[RatingDelta] = []
        for index, rating in enumerate(ratings):
            after_mu = rating.mu + movement * (outcomes[index] - expected[index])
            after_sigma = max(MIN_SIGMA, rating.sigma * (1 - 0.03 * multiplier))
            deltas.append(
                RatingDelta(
                    rating.fleet_id,
                    rating.mu,
                    rating.sigma,
                    after_mu,
                    after_sigma,
                    rating.display_score,
                    display_score(after_mu, after_sigma),
                )
            )
        return deltas[0], deltas[1]

    def apply_once(self, session: Session, match_id: Any) -> RatingEvent:
        existing = session.scalar(select(RatingEvent).where(RatingEvent.match_id == match_id))
        if existing is not None:
            return existing
        match = session.get(Match, match_id)
        if (
            match is None
            or match.mode != MatchMode.RANKED
            or match.status != MatchStatus.FINISHED
            or not isinstance(match.result, dict)
            or match.result.get("reason") == "failed"
            or match.result.get("winnerSlot") not in (0, 1)
        ):
            raise RatingError("training, failed, or unattributed matches are not scoreable")
        participants = session.execute(
            select(MatchParticipant, Fleet)
            .join(Fleet, Fleet.id == MatchParticipant.fleet_id)
            .where(MatchParticipant.match_id == match.id)
            .order_by(MatchParticipant.slot)
            .with_for_update()
        ).all()
        if len(participants) != 2 or [item[0].slot for item in participants] != [0, 1]:
            raise RatingError("ranked match requires exactly two attributed slots")
        rating_rows: list[Rating] = []
        for participant, _fleet in participants:
            rating = session.get(Rating, participant.fleet_id)
            if rating is None:
                rating = Rating(
                    fleet_id=participant.fleet_id,
                    mu=DEFAULT_MU,
                    sigma=DEFAULT_SIGMA,
                    display_score=display_score(DEFAULT_MU, DEFAULT_SIGMA),
                )
                session.add(rating)
                session.flush()
            rating_rows.append(rating)

        event = RatingEvent(match_id=match.id, changes=[])
        session.add(event)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            concurrent = session.scalar(select(RatingEvent).where(RatingEvent.match_id == match_id))
            if concurrent is None:
                raise
            return concurrent
        deltas = self.preview(
            (rating_rows[0], rating_rows[1]),
            int(match.result["winnerSlot"]),
            multiplier=match.rating_multiplier,
        )
        changes: list[dict[str, Any]] = []
        for delta, rating, (_participant, fleet) in zip(
            deltas, rating_rows, participants, strict=True
        ):
            changes.append(delta.as_json(fleet))
            rating.mu = delta.after_mu
            rating.sigma = delta.after_sigma
            rating.display_score = delta.after_score
            rating.updated_at = utc_now()
        event.changes = changes
        session.commit()
        session.refresh(event)
        return event
