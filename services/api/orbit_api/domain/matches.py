"""Immutable match creation and queue orchestration."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Literal

from orbit_engine import PINNED_RULESET_ID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    StrategyStatus,
    StrategyVersion,
    User,
)
from orbit_api.domain.matchmaking import Matchmaker, MatchmakingError
from orbit_api.infrastructure.match_queue import MatchQueue
from orbit_api.security.oidc import Principal
from orbit_api.security.public_ids import new_public_id


class MatchCreationError(RuntimeError):
    code = "match.invalid_request"


class MatchCreationConflict(MatchCreationError):
    code = "match.idempotency_conflict"


class MatchNotFound(MatchCreationError):
    code = "match.not_found"


class HumanRankedNotAllowed(MatchCreationError):
    code = "match.human_training_only"


@dataclass(frozen=True)
class MatchCreationRequest:
    fleet_id: str
    opponent_fleet_id: str
    mode: Literal["training", "ranked"]
    controller_type: Literal["human", "agent"]
    opponent_controller_type: Literal["human", "agent"]
    map_id: str


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def match_request_key(subject: str, idempotency_key: str) -> str:
    """Return the stable stored key for an owner-scoped idempotent match request."""
    return _hash(["match", subject, idempotency_key])


def _owned_fleet(session: Session, principal: Principal, public_id: str) -> Fleet:
    fleet = session.scalar(
        select(Fleet)
        .join(User, User.id == Fleet.owner_user_id)
        .where(Fleet.public_id == public_id, User.oidc_subject == principal.subject)
    )
    if fleet is None:
        raise MatchCreationError("requesting fleet is unavailable")
    return fleet


def _version_for(
    session: Session, fleet: Fleet, controller: ControllerType
) -> StrategyVersion | None:
    if controller == ControllerType.HUMAN:
        return None
    version = session.get(StrategyVersion, fleet.current_strategy_version_id)
    if version is None or version.status != StrategyStatus.READY:
        raise MatchCreationError("agent controller requires a ready current strategy")
    return version


def create_match(
    session: Session,
    queue: MatchQueue,
    principal: Principal,
    request: MatchCreationRequest,
    *,
    idempotency_key: str,
) -> tuple[Match, int, bool]:
    if not idempotency_key or len(idempotency_key) > 128:
        raise MatchCreationError("an idempotency key is required")
    fleet = _owned_fleet(session, principal, request.fleet_id)
    opponent = session.scalar(select(Fleet).where(Fleet.public_id == request.opponent_fleet_id))
    if opponent is None or opponent.id == fleet.id:
        raise MatchCreationError("opponent fleet is unavailable")
    try:
        own_controller = ControllerType(request.controller_type)
        opponent_controller = ControllerType(request.opponent_controller_type)
        mode = MatchMode(request.mode)
    except ValueError as error:
        raise MatchCreationError("unsupported mode or controller") from error
    if mode == MatchMode.RANKED and ControllerType.HUMAN in {
        own_controller,
        opponent_controller,
    }:
        raise HumanRankedNotAllowed("human control is limited to training matches")
    own_version = _version_for(session, fleet, own_controller)
    opponent_version = _version_for(session, opponent, opponent_controller)
    payload = {
        "fleet": fleet.public_id,
        "opponent": opponent.public_id,
        "mode": mode.value,
        "controller": own_controller.value,
        "opponentController": opponent_controller.value,
        "map": request.map_id,
    }
    request_hash = _hash(payload)
    request_key = match_request_key(principal.subject, idempotency_key)
    existing = session.scalar(select(Match).where(Match.request_key == request_key))
    if existing is not None:
        if existing.request_hash != request_hash:
            raise MatchCreationConflict("idempotency key already has another payload")
        participant = session.scalar(
            select(MatchParticipant).where(
                MatchParticipant.match_id == existing.id,
                MatchParticipant.fleet_id == fleet.id,
            )
        )
        if participant is None:
            raise MatchCreationError("stored match attribution is incomplete")
        queue.enqueue(existing.public_id)
        return existing, participant.slot, True

    try:
        offer = (
            Matchmaker().challenge(session, fleet, opponent) if mode == MatchMode.RANKED else None
        )
    except MatchmakingError as error:
        raise MatchCreationError(str(error)) from error

    own_slot = secrets.randbelow(2)
    match = Match(
        public_id=new_public_id("match"),
        ruleset_id=PINNED_RULESET_ID,
        map_id=request.map_id,
        seed=secrets.randbelow(2**63 - 1),
        request_key=request_key,
        request_hash=request_hash,
        mode=mode,
        status=MatchStatus.QUEUED,
        matchmaking_reason=offer.reason if offer else "training_direct",
        rating_multiplier=offer.rating_multiplier if offer else 0.0,
    )
    session.add(match)
    session.flush()
    participants = (
        (fleet, own_slot, own_controller, own_version),
        (opponent, 1 - own_slot, opponent_controller, opponent_version),
    )
    session.add_all(
        MatchParticipant(
            match_id=match.id,
            fleet_id=participant_fleet.id,
            slot=slot,
            controller_type=controller,
            strategy_version_id=version.id if version else None,
        )
        for participant_fleet, slot, controller, version in participants
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise MatchCreationError("match creation conflicted; retry safely") from None
    session.refresh(match)
    queue.enqueue(match.public_id)
    return match, own_slot, False


def match_for_fleet(session: Session, public_id: str, fleet: Fleet) -> Match:
    match = session.scalar(
        select(Match)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(Match.public_id == public_id, MatchParticipant.fleet_id == fleet.id)
    )
    if match is None:
        raise MatchNotFound("match was not found")
    return match
