"""Idempotent system-agent provisioning for a usable empty competition."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.models import Fleet, Match, Rating, User
from orbit_api.domain.fleets import create_fleet
from orbit_api.domain.matches import (
    MatchCreationRequest,
    create_match,
    match_request_key,
)
from orbit_api.domain.ratings import DEFAULT_MU, DEFAULT_SIGMA, display_score
from orbit_api.infrastructure.match_queue import MatchQueue
from orbit_api.security.oidc import Principal


@dataclass(frozen=True, slots=True)
class WarmupAgent:
    slug: str
    name: str
    commander_code: str
    declaration: str
    strategy_tendency: str
    strategy_template: str
    style_description: str

    @property
    def subject(self) -> str:
        return f"orbit:system:warmup:{self.slug}"

    @property
    def principal(self) -> Principal:
        return Principal(self.subject, {"name": f"System Agent · {self.name}"})

    def fleet_payload(self) -> dict[str, str]:
        return {
            "name": self.name,
            "commander_code": self.commander_code,
            "declaration": self.declaration,
            "strategy_tendency": self.strategy_tendency,
            "strategy_template": self.strategy_template,
            "style_description": self.style_description,
        }


WARMUP_AGENTS = (
    WarmupAgent(
        "amber-relay",
        "Amber Relay",
        "WARM-01",
        "Signals first, momentum second.",
        "balanced",
        "platform-basic",
        "A compact amber frame built around a bright circular relay mast.",
    ),
    WarmupAgent(
        "vanta-meridian",
        "Vanta Meridian",
        "WARM-02",
        "Every dark arc hides a faster route.",
        "assault",
        "kaggle-structured-v11",
        "A matte black crescent hull traced with thin violet navigation lines.",
    ),
    WarmupAgent(
        "helix-bastion",
        "Helix Bastion",
        "WARM-03",
        "Hold the center and let the orbit turn.",
        "defense",
        "platform-basic",
        "A layered graphite citadel with twin helical sensor rings.",
    ),
    WarmupAgent(
        "pale-vector",
        "Pale Vector",
        "WARM-04",
        "Claim the quiet lanes before they close.",
        "expansion",
        "kaggle-structured-v11",
        "A slender pearl hull with long fins aligned to a single clean vector.",
    ),
    WarmupAgent(
        "copper-apogee",
        "Copper Apogee",
        "WARM-05",
        "Pressure rises at the farthest point.",
        "assault",
        "platform-basic",
        "A burnished copper wedge surrounded by a sparse crown of signal vanes.",
    ),
    WarmupAgent(
        "silent-periapsis",
        "Silent Periapsis",
        "WARM-06",
        "Close distance, conserve force, leave no noise.",
        "balanced",
        "kaggle-structured-v11",
        "A low silver spindle with recessed blue engines and no exposed bridge.",
    ),
)

WARMUP_FIXTURES = tuple(
    (index, (index + 1) % len(WARMUP_AGENTS)) for index in range(len(WARMUP_AGENTS))
)


@dataclass(frozen=True, slots=True)
class WarmupResult:
    fleet_public_ids: tuple[str, ...]
    match_public_ids: tuple[str, ...]
    created_fleets: int
    created_matches: int


def _fleet_for_subject(session: Session, subject: str) -> Fleet | None:
    return session.scalar(
        select(Fleet).join(User, User.id == Fleet.owner_user_id).where(User.oidc_subject == subject)
    )


def _ensure_agents(session: Session) -> tuple[tuple[Fleet, ...], int]:
    fleets: list[Fleet] = []
    created = 0
    for agent in WARMUP_AGENTS:
        fleet = _fleet_for_subject(session, agent.subject)
        if fleet is None:
            fleet = create_fleet(session, agent.principal, agent.fleet_payload())
            created += 1
        if session.get(Rating, fleet.id) is None:
            session.add(
                Rating(
                    fleet_id=fleet.id,
                    mu=DEFAULT_MU,
                    sigma=DEFAULT_SIGMA,
                    display_score=display_score(DEFAULT_MU, DEFAULT_SIGMA),
                )
            )
        fleets.append(fleet)
    session.commit()
    return tuple(fleets), created


def provision_warmup(
    session: Session,
    queue: MatchQueue,
    *,
    match_count: int = len(WARMUP_FIXTURES),
) -> WarmupResult:
    """Create the system-agent pool and queue each stable warm-up fixture once."""
    if not 0 <= match_count <= len(WARMUP_FIXTURES):
        raise ValueError(f"match_count must be between 0 and {len(WARMUP_FIXTURES)}")

    fleets, created_fleets = _ensure_agents(session)
    match_ids: list[str] = []
    created_matches = 0
    for left_index, right_index in WARMUP_FIXTURES[:match_count]:
        owner = WARMUP_AGENTS[left_index]
        left = fleets[left_index]
        right = fleets[right_index]
        idempotency_key = f"warmup-v1:{owner.slug}:{WARMUP_AGENTS[right_index].slug}"
        stored_key = match_request_key(owner.subject, idempotency_key)
        existing = session.scalar(select(Match).where(Match.request_key == stored_key))
        if existing is not None:
            match_ids.append(existing.public_id)
            continue
        match, _slot, _replayed = create_match(
            session,
            queue,
            owner.principal,
            MatchCreationRequest(
                fleet_id=left.public_id,
                opponent_fleet_id=right.public_id,
                mode="ranked",
                controller_type="agent",
                opponent_controller_type="agent",
                map_id="orbit-standard-v1",
            ),
            idempotency_key=idempotency_key,
        )
        match_ids.append(match.public_id)
        created_matches += 1

    return WarmupResult(
        fleet_public_ids=tuple(fleet.public_id for fleet in fleets),
        match_public_ids=tuple(match_ids),
        created_fleets=created_fleets,
        created_matches=created_matches,
    )
