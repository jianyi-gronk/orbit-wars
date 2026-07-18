"""Training simulation orchestration with immutable match attribution."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any, Literal

from orbit_engine import PINNED_RULESET_ID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.builtin_strategies.registry import ALL_BUILTINS, BuiltinStrategy
from orbit_api.db.base import utc_now
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    ReplayArtifact,
    StrategyStatus,
    StrategyVersion,
    User,
)
from orbit_api.security.public_ids import new_public_id

MAPS: dict[str, dict[str, str]] = {
    "orbit-standard-v1": {"name": "Standard Orbit", "density": "balanced"},
    "orbit-drift-v1": {"name": "Drift Lanes", "density": "open"},
    "orbit-crown-v1": {"name": "Crown Cluster", "density": "dense"},
}


class SimulationError(RuntimeError):
    code = "simulation.error"


class SimulationNotFoundError(SimulationError):
    code = "simulation.not_found"


class SimulationConflictError(SimulationError):
    code = "simulation.idempotency_conflict"


class SimulationInputError(SimulationError):
    code = "simulation.invalid_request"


@dataclass(frozen=True)
class SimulationRequest:
    map_id: str
    opponent_type: Literal["builtin", "public"]
    opponent_id: str
    strategy_version_id: str | None = None


@dataclass(frozen=True)
class CandidateStrategy:
    content_hash: str
    object_key: str
    manifest: dict[str, Any]
    runtime_image: str
    submitted_by: str
    validation: dict[str, Any]


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _ready_version(session: Session, fleet: Fleet, public_id: str | None) -> StrategyVersion:
    version = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.id == fleet.current_strategy_version_id
            if public_id is None
            else StrategyVersion.public_id == public_id,
            StrategyVersion.fleet_id == fleet.id,
        )
    )
    if version is None or version.status != StrategyStatus.READY:
        raise SimulationInputError("a ready strategy version is required")
    return version


def _builtin_by_slug(slug: str) -> BuiltinStrategy:
    for builtin in ALL_BUILTINS:
        if builtin.slug == slug:
            return builtin
    raise SimulationInputError("unknown built-in opponent")


def _ensure_builtin_fleet(
    session: Session, builtin: BuiltinStrategy
) -> tuple[Fleet, StrategyVersion]:
    subject = f"system:training:{builtin.slug}"
    user = session.scalar(select(User).where(User.oidc_subject == subject))
    if user is None:
        user = User(oidc_subject=subject, display_name=builtin.title)
        session.add(user)
        session.flush()
    fleet = session.scalar(select(Fleet).where(Fleet.owner_user_id == user.id))
    if fleet is None:
        fleet = Fleet(
            public_id=new_public_id("fleet"),
            owner_user_id=user.id,
            name=builtin.title,
            commander_code=f"BOT-{builtin.slug[:12]}",
            declaration="Platform training opponent.",
            style_description="An original autonomous training silhouette with a cool signal halo.",
            strategy_tendency="balanced",
        )
        session.add(fleet)
        session.flush()
    version = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.fleet_id == fleet.id,
            StrategyVersion.content_hash == builtin.content_hash,
        )
    )
    if version is None:
        package = builtin.package_bytes()
        version = StrategyVersion(
            public_id=new_public_id("strategy"),
            fleet_id=fleet.id,
            content_hash=builtin.content_hash,
            object_key=f"builtin://{builtin.slug}",
            manifest={
                "schemaVersion": 1,
                "entrypoint": builtin.entrypoint,
                "builtin": builtin.slug,
            },
            notes="Audited platform training opponent",
            source="builtin",
            submitted_by="platform",
            runtime_image=builtin.runtime_image,
            package_size_bytes=len(package),
            validation_report={"result": "ready", "checks": ["audited_builtin"]},
            validated_at=utc_now(),
            status=StrategyStatus.READY,
        )
        session.add(version)
        session.flush()
    fleet.current_strategy_version_id = version.id
    return fleet, version


def _resolve_opponent(
    session: Session, fleet: Fleet, request: SimulationRequest
) -> tuple[Fleet, StrategyVersion]:
    if request.opponent_type == "builtin":
        return _ensure_builtin_fleet(session, _builtin_by_slug(request.opponent_id))
    opponent = session.scalar(select(Fleet).where(Fleet.public_id == request.opponent_id))
    if opponent is None or opponent.id == fleet.id:
        raise SimulationInputError("public opponent is unavailable")
    return opponent, _ready_version(session, opponent, None)


def create_simulation(
    session: Session,
    fleet: Fleet,
    request: SimulationRequest,
    *,
    idempotency_key: str,
    actor_key: str,
    candidate: CandidateStrategy | None = None,
) -> tuple[Match, bool]:
    if request.map_id not in MAPS:
        raise SimulationInputError("unknown map")
    if not idempotency_key.strip() or len(idempotency_key) > 128:
        raise SimulationInputError("an idempotency key of at most 128 characters is required")
    if candidate is not None and request.strategy_version_id is not None:
        raise SimulationInputError("candidate package and strategy version are mutually exclusive")
    source = (
        None
        if candidate is not None
        else _ready_version(session, fleet, request.strategy_version_id)
    )
    opponent, opponent_version = _resolve_opponent(session, fleet, request)
    payload = {
        "map": request.map_id,
        "opponentType": request.opponent_type,
        "opponentId": request.opponent_id,
        "strategyVersionId": source.public_id if source else None,
        "candidateContentHash": candidate.content_hash if candidate else None,
    }
    request_hash = _hash_json(payload)
    stored_key = _hash_json([fleet.public_id, actor_key, idempotency_key])
    existing = session.scalar(select(Match).where(Match.request_key == stored_key))
    if existing is not None:
        if existing.request_hash != request_hash:
            raise SimulationConflictError("idempotency key was already used for another request")
        return existing, True
    match = Match(
        public_id=new_public_id("match"),
        ruleset_id=PINNED_RULESET_ID,
        map_id=request.map_id,
        seed=secrets.randbelow(2**63 - 1),
        request_key=stored_key,
        request_hash=request_hash,
        mode=MatchMode.TRAINING,
        status=MatchStatus.QUEUED,
    )
    session.add(match)
    session.flush()
    session.add_all(
        [
            MatchParticipant(
                match_id=match.id,
                fleet_id=fleet.id,
                slot=0,
                controller_type=ControllerType.AGENT,
                strategy_version_id=source.id if source else None,
                candidate_content_hash=candidate.content_hash if candidate else None,
                candidate_object_key=candidate.object_key if candidate else None,
                candidate_manifest=candidate.manifest if candidate else None,
                candidate_runtime_image=candidate.runtime_image if candidate else None,
                candidate_submitted_by=candidate.submitted_by if candidate else None,
                candidate_validation=candidate.validation if candidate else None,
            ),
            MatchParticipant(
                match_id=match.id,
                fleet_id=opponent.id,
                slot=1,
                controller_type=ControllerType.AGENT,
                strategy_version_id=opponent_version.id,
            ),
        ]
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(Match).where(Match.request_key == stored_key))
        if existing is None or existing.request_hash != request_hash:
            raise
        return existing, True
    session.refresh(match)
    return match, False


def get_simulation(session: Session, fleet: Fleet, public_id: str) -> Match:
    match = session.scalar(
        select(Match)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(
            Match.public_id == public_id,
            Match.mode == MatchMode.TRAINING,
            MatchParticipant.fleet_id == fleet.id,
        )
    )
    if match is None:
        raise SimulationNotFoundError("simulation was not found")
    return match


def simulation_response(session: Session, match: Match) -> dict[str, Any]:
    replay = session.get(ReplayArtifact, match.replay_id) if match.replay_id else None
    participants = session.execute(
        select(MatchParticipant, Fleet, StrategyVersion)
        .join(Fleet, Fleet.id == MatchParticipant.fleet_id)
        .outerjoin(StrategyVersion, StrategyVersion.id == MatchParticipant.strategy_version_id)
        .where(MatchParticipant.match_id == match.id)
        .order_by(MatchParticipant.slot)
    ).all()
    return {
        "publicId": match.public_id,
        "mode": match.mode,
        "status": match.status,
        "rulesetId": match.ruleset_id,
        "mapId": match.map_id,
        "seed": match.seed,
        "result": match.result,
        "createdAt": match.created_at,
        "finishedAt": match.finished_at,
        "replayPublicId": replay.public_id if replay else None,
        "participants": [
            {
                "slot": participant.slot,
                "fleetPublicId": participant_fleet.public_id,
                "fleetName": participant_fleet.name,
                "controllerType": participant.controller_type,
                "strategyVersionId": version.public_id if version else None,
                "candidate": (
                    {
                        "contentHash": participant.candidate_content_hash,
                        "submittedBy": participant.candidate_submitted_by,
                        "runtimeImage": participant.candidate_runtime_image,
                        "validation": participant.candidate_validation,
                    }
                    if participant.candidate_content_hash
                    else None
                ),
            }
            for participant, participant_fleet, version in participants
        ],
    }


def finish_simulation(
    session: Session,
    public_id: str,
    *,
    result: dict[str, Any] | None,
    failed: bool = False,
) -> Match:
    match = session.scalar(
        select(Match).where(Match.public_id == public_id, Match.mode == MatchMode.TRAINING)
    )
    if match is None:
        raise SimulationNotFoundError("simulation was not found")
    match.status = MatchStatus.FAILED if failed else MatchStatus.FINISHED
    match.result = result
    match.finished_at = utc_now()
    session.commit()
    session.refresh(match)
    return match
