"""Scoped Agent API and owner-managed Agent Key lifecycle."""

from __future__ import annotations

import base64
import binascii
import hashlib
import threading
import time
from collections import defaultdict, deque
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.models import (
    AgentKey,
    Fleet,
    Match,
    MatchParticipant,
    ReplayArtifact,
    StrategyVersion,
    User,
)
from orbit_api.db.session import database_session
from orbit_api.domain.agent_keys import (
    ALLOWED_SCOPES,
    AgentKeyContext,
    AgentKeyError,
    AgentKeyInvalidError,
    AgentKeyScopeError,
    authenticate_agent_key,
    issue_agent_key,
    revoke_agent_key,
)
from orbit_api.domain.fleets import FleetError, get_owned_fleet
from orbit_api.domain.matches import (
    MatchCreationError,
    MatchCreationRequest,
    create_match,
)
from orbit_api.domain.simulations import (
    CandidateStrategy,
    SimulationConflictError,
    SimulationError,
    SimulationRequest,
    create_simulation,
    get_simulation,
    simulation_response,
)
from orbit_api.domain.strategy_validation import (
    DockerSandboxSession,
    StrategyValidationError,
    StrategyValidationUnavailable,
    validate_package,
    validate_strategy_version,
)
from orbit_api.domain.strategy_versions import (
    StrategyVersionError,
    inspect_package,
    publish_strategy_version,
    set_current_strategy,
)
from orbit_api.infrastructure.match_queue import RedisMatchQueue
from orbit_api.security.oidc import Principal, current_principal
from orbit_api.storage.strategy_packages import (
    S3StrategyPackageStore,
    StrategyPackageStore,
)


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: _camel(value), populate_by_name=True)


class AgentKeyCreateRequest(APIModel):
    scopes: list[str] = Field(min_length=1, max_length=len(ALLOWED_SCOPES))


class AgentKeyCreatedResponse(APIModel):
    key: str
    public_prefix: str
    scopes: list[str]


class VersionPublishRequest(APIModel):
    package_base64: str
    notes: str = ""
    source: str = "agent-api"
    submitted_by: str = "external-agent"


class SimulationCreateRequest(APIModel):
    map_id: str = "orbit-standard-v1"
    opponent_type: Literal["builtin", "public"] = "builtin"
    opponent_id: str = "training-v1"
    strategy_version_id: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    candidate_package_base64: str | None = None
    candidate_notes: str = ""
    submitted_by: str = Field(default="external-agent", min_length=1, max_length=120)

    @model_validator(mode="after")
    def one_strategy_source(self) -> SimulationCreateRequest:
        if self.candidate_package_base64 and self.strategy_version_id:
            raise ValueError("candidatePackageBase64 and strategyVersionId are mutually exclusive")
        return self


class ChallengeCreateRequest(APIModel):
    opponent_fleet_id: str
    opponent_controller_type: Literal["human", "agent"] = "agent"
    map_id: str = "orbit-standard-v1"
    idempotency_key: str = Field(min_length=1, max_length=128)


class CurrentVersionRequest(APIModel):
    strategy_version_id: str


class SlidingWindowLimiter:
    def __init__(self, limit: int = 60, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        now = time.monotonic()
        with self.lock:
            events = self.events[identity]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


router = APIRouter()
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]
_default_limiter = SlidingWindowLimiter()
_default_simulation_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)


def strategy_store(request: Request) -> StrategyPackageStore:
    store = getattr(request.app.state, "strategy_package_store", None)
    if store is None:
        store = S3StrategyPackageStore.from_environment()
        request.app.state.strategy_package_store = store
    return store


def _agent_context(
    request: Request,
    session: Session,
    scope: str,
) -> AgentKeyContext:
    scheme, _, credential = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(status_code=401, detail={"code": "agent_key.required"})
    try:
        context = authenticate_agent_key(session, credential, required_scope=scope)
    except AgentKeyInvalidError as error:
        raise HTTPException(status_code=401, detail={"code": error.code}) from error
    except AgentKeyScopeError as error:
        raise HTTPException(status_code=403, detail={"code": error.code}) from error
    limiter = getattr(request.app.state, "agent_rate_limiter", _default_limiter)
    if not limiter.allow(context.key.public_prefix):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "agent.rate_limited"},
            headers={"Retry-After": "60"},
        )
    return context


def _simulation_limit(request: Request, context: AgentKeyContext) -> None:
    limiter = getattr(request.app.state, "simulation_rate_limiter", _default_simulation_limiter)
    identities = (
        f"fleet:{context.fleet.id}",
        f"agent-key:{context.key.public_prefix}",
    )
    if any(not limiter.allow(identity) for identity in identities):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "simulation.rate_limited"},
            headers={"Retry-After": "60"},
        )


def _simulation_error(error: SimulationError) -> HTTPException:
    if error.code == "simulation.not_found":
        response_status = 404
    elif isinstance(error, SimulationConflictError):
        response_status = 409
    else:
        response_status = 422
    return HTTPException(response_status, detail={"code": error.code, "message": str(error)})


def _validated_candidate(
    payload: SimulationCreateRequest,
    request: Request,
    context: AgentKeyContext,
    store: StrategyPackageStore,
) -> CandidateStrategy | None:
    encoded = payload.candidate_package_base64
    if not encoded:
        return None
    try:
        package = base64.b64decode(encoded, validate=True)
        manifest = inspect_package(package)
    except (ValueError, binascii.Error, StrategyVersionError) as error:
        raise HTTPException(422, detail={"code": "strategy.invalid_package"}) from error
    runtime_image = "orbit-agent-sandbox:py311-stdlib-v1"
    sandbox_factory = getattr(request.app.state, "strategy_sandbox_factory", DockerSandboxSession)
    try:
        report = validate_package(
            package,
            runtime_image=runtime_image,
            sandbox_factory=sandbox_factory,
        )
    except StrategyValidationError as error:
        raise HTTPException(
            422, detail={"code": error.code, "message": error.safe_message}
        ) from error
    except StrategyValidationUnavailable as error:
        raise HTTPException(503, detail={"code": "strategy.validation_unavailable"}) from error
    content_hash = hashlib.sha256(package).hexdigest()
    object_key = f"fleets/{context.fleet.public_id}/simulation-candidates/{content_hash}.zip"
    store.put_immutable(object_key, package)
    return CandidateStrategy(
        content_hash=content_hash,
        object_key=object_key,
        manifest=manifest,
        runtime_image=runtime_image,
        submitted_by=payload.submitted_by,
        validation={**report.as_json(), "notes": payload.candidate_notes[:1000]},
    )


@router.post("/api/v1/fleets/{public_id}/agent-keys", status_code=201)
def create_key(
    public_id: str,
    payload: AgentKeyCreateRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> AgentKeyCreatedResponse:
    try:
        issued = issue_agent_key(session, principal, public_id, payload.scopes)
    except (AgentKeyError, FleetError) as error:
        raise HTTPException(status_code=422, detail={"code": error.code}) from error
    return AgentKeyCreatedResponse(
        key=issued.credential,
        public_prefix=issued.public_prefix,
        scopes=list(issued.scopes),
    )


@router.delete("/api/v1/fleets/{public_id}/agent-keys/{public_prefix}", status_code=204)
def revoke_key(
    public_id: str,
    public_prefix: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> None:
    try:
        revoke_agent_key(session, principal, public_id, public_prefix)
    except FleetError as error:
        raise HTTPException(status_code=404, detail={"code": error.code}) from error


@router.get("/api/v1/fleets/{public_id}/agent-keys")
def list_keys(
    public_id: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> list[dict[str, Any]]:
    try:
        fleet = get_owned_fleet(session, principal, public_id)
    except FleetError as error:
        raise HTTPException(status_code=404, detail={"code": error.code}) from error
    keys = session.scalars(
        select(AgentKey).where(AgentKey.fleet_id == fleet.id).order_by(AgentKey.created_at.desc())
    )
    return [
        {
            "publicPrefix": key.public_prefix,
            "scopes": key.scopes,
            "active": key.revoked_at is None,
            "createdAt": key.created_at,
            "lastUsedAt": key.last_used_at,
            "revokedAt": key.revoked_at,
        }
        for key in keys
    ]


@router.patch("/api/v1/fleets/{public_id}/current-strategy")
def select_current_version(
    public_id: str,
    payload: CurrentVersionRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, Any]:
    try:
        version = set_current_strategy(
            session,
            principal,
            public_id,
            payload.strategy_version_id,
        )
    except (FleetError, StrategyVersionError) as error:
        raise HTTPException(status_code=422, detail={"code": error.code}) from error
    return _version_response(version)


@router.get("/api/agent/v1/fleet")
def agent_fleet(request: Request, session: SessionDependency) -> dict[str, Any]:
    context = _agent_context(request, session, "fleet:read")
    fleet = context.fleet
    return {
        "publicId": fleet.public_id,
        "name": fleet.name,
        "commanderCode": fleet.commander_code,
        "strategyTendency": fleet.strategy_tendency,
    }


@router.get("/api/agent/v1/versions")
def agent_versions(request: Request, session: SessionDependency) -> list[dict[str, Any]]:
    context = _agent_context(request, session, "version:read")
    versions = session.scalars(
        select(StrategyVersion)
        .where(StrategyVersion.fleet_id == context.fleet.id)
        .order_by(StrategyVersion.created_at.desc())
    )
    return [_version_response(version) for version in versions]


@router.post("/api/agent/v1/versions", status_code=201)
def agent_publish_version(
    payload: VersionPublishRequest,
    request: Request,
    session: SessionDependency,
    store: Annotated[StrategyPackageStore, Depends(strategy_store)],
) -> dict[str, Any]:
    context = _agent_context(request, session, "version:write")
    try:
        package = base64.b64decode(payload.package_base64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise HTTPException(status_code=422, detail={"code": "strategy.invalid_base64"}) from error
    owner = session.get(User, context.fleet.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=401, detail={"code": "agent_key.invalid"})
    publication = publish_strategy_version(
        session,
        store,
        Principal(subject=owner.oidc_subject, claims={}),
        context.fleet.public_id,
        package,
        notes=payload.notes,
        source=payload.source,
        submitted_by=payload.submitted_by,
        runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
    )
    version = publication.version
    if version.status == "uploaded":
        sandbox_factory = getattr(
            request.app.state,
            "strategy_sandbox_factory",
            DockerSandboxSession,
        )
        version = validate_strategy_version(
            session,
            store,
            version.public_id,
            sandbox_factory=sandbox_factory,
        )
    return {**_version_response(version), "deduplicated": publication.deduplicated}


@router.get("/api/agent/v1/opponents")
def agent_opponents(request: Request, session: SessionDependency) -> list[dict[str, str]]:
    context = _agent_context(request, session, "opponents:read")
    opponents = session.scalars(
        select(Fleet)
        .where(Fleet.id != context.fleet.id)
        .order_by(Fleet.created_at.desc())
        .limit(50)
    )
    return [
        {"publicId": fleet.public_id, "name": fleet.name, "commanderCode": fleet.commander_code}
        for fleet in opponents
    ]


@router.get("/api/agent/v1/matches")
def agent_matches(request: Request, session: SessionDependency) -> list[dict[str, Any]]:
    context = _agent_context(request, session, "matches:read")
    matches = session.scalars(
        select(Match)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .where(MatchParticipant.fleet_id == context.fleet.id)
        .order_by(Match.created_at.desc())
        .limit(50)
    )
    response: list[dict[str, Any]] = []
    for match in matches:
        participant = session.scalar(
            select(MatchParticipant).where(
                MatchParticipant.match_id == match.id,
                MatchParticipant.fleet_id == context.fleet.id,
            )
        )
        version = (
            session.get(StrategyVersion, participant.strategy_version_id)
            if participant and participant.strategy_version_id
            else None
        )
        replay = session.get(ReplayArtifact, match.replay_id) if match.replay_id else None
        response.append(
            {
                "publicId": match.public_id,
                "mode": match.mode,
                "status": match.status,
                "mapId": match.map_id,
                "result": match.result,
                "controllerType": participant.controller_type if participant else None,
                "strategyVersionId": version.public_id if version else None,
                "candidateContentHash": (
                    participant.candidate_content_hash if participant else None
                ),
                "replayPublicId": replay.public_id if replay and replay.is_public else None,
                "createdAt": match.created_at,
                "finishedAt": match.finished_at,
            }
        )
    return response


@router.post("/api/agent/v1/challenges", status_code=201)
def agent_create_challenge(
    payload: ChallengeCreateRequest,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    context = _agent_context(request, session, "challenge")
    owner = session.get(User, context.fleet.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=401, detail={"code": "agent_key.invalid"})
    queue = getattr(request.app.state, "match_queue", None)
    if queue is None:
        queue = RedisMatchQueue.from_environment()
        request.app.state.match_queue = queue
    try:
        match, slot, replayed = create_match(
            session,
            queue,
            Principal(subject=owner.oidc_subject, claims={}),
            MatchCreationRequest(
                fleet_id=context.fleet.public_id,
                opponent_fleet_id=payload.opponent_fleet_id,
                mode="ranked",
                controller_type="agent",
                opponent_controller_type=payload.opponent_controller_type,
                map_id=payload.map_id,
            ),
            idempotency_key=payload.idempotency_key,
        )
    except MatchCreationError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return {
        "publicId": match.public_id,
        "status": match.status,
        "playerSlot": slot,
        "matchmakingReason": match.matchmaking_reason,
        "ratingMultiplier": match.rating_multiplier,
        "idempotentReplay": replayed,
    }


@router.post("/api/agent/v1/simulations", status_code=201)
def agent_create_simulation(
    payload: SimulationCreateRequest,
    request: Request,
    session: SessionDependency,
    store: Annotated[StrategyPackageStore, Depends(strategy_store)],
) -> dict[str, Any]:
    context = _agent_context(request, session, "simulate")
    _simulation_limit(request, context)
    try:
        candidate = _validated_candidate(payload, request, context, store)
        match, replayed = create_simulation(
            session,
            context.fleet,
            SimulationRequest(
                map_id=payload.map_id,
                opponent_type=payload.opponent_type,
                opponent_id=payload.opponent_id,
                strategy_version_id=payload.strategy_version_id,
            ),
            idempotency_key=payload.idempotency_key,
            actor_key=f"agent:{context.key.public_prefix}",
            candidate=candidate,
        )
    except SimulationError as error:
        raise _simulation_error(error) from error
    queue = getattr(request.app.state, "match_queue", None)
    if queue is None:
        queue = RedisMatchQueue.from_environment()
        request.app.state.match_queue = queue
    if not replayed:
        queue.enqueue(match.public_id)
    return {**simulation_response(session, match), "idempotentReplay": replayed}


@router.get("/api/agent/v1/simulations/{simulation_id}")
def agent_read_simulation(
    simulation_id: str,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    context = _agent_context(request, session, "simulate")
    try:
        return simulation_response(
            session,
            get_simulation(session, context.fleet, simulation_id),
        )
    except SimulationError as error:
        raise _simulation_error(error) from error


def _version_response(version: StrategyVersion) -> dict[str, Any]:
    return {
        "publicId": version.public_id,
        "contentHash": version.content_hash,
        "status": version.status,
        "notes": version.notes,
        "runtimeImage": version.runtime_image,
        "createdAt": version.created_at,
        "validation": version.validation_report,
    }
