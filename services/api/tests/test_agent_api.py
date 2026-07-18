import asyncio
import base64
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, Request
from orbit_api.api.agent import SlidingWindowLimiter
from orbit_api.builtin_strategies.registry import TRAINING
from orbit_api.db.base import Base
from orbit_api.db.models import (
    AgentKey,
    Fleet,
    Match,
    MatchParticipant,
    RatingEvent,
    StrategyVersion,
)
from orbit_api.db.session import database_session
from orbit_api.domain.simulations import finish_simulation
from orbit_api.domain.strategy_validation import LocalSandboxSession
from orbit_api.infrastructure.match_queue import MemoryMatchQueue
from orbit_api.main import app
from orbit_api.security.oidc import Principal, current_principal
from orbit_api.storage.strategy_packages import StoredPackage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_immutable(self, key: str, content: bytes) -> StoredPackage:
        created = key not in self.objects
        self.objects.setdefault(key, content)
        return StoredPackage(key, created)

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture
def agent_client(tmp_path: Path) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/agent-api.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def test_principal(request: Request) -> Principal:
        subject = request.headers.get("X-Test-Subject")
        if not subject:
            raise HTTPException(status_code=401)
        return Principal(subject=subject, claims={})

    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    app.state.strategy_package_store = MemoryStore()
    app.state.strategy_sandbox_factory = LocalSandboxSession
    app.state.agent_rate_limiter = SlidingWindowLimiter(limit=100)
    app.state.simulation_rate_limiter = SlidingWindowLimiter(limit=100)
    app.state.match_queue = MemoryMatchQueue()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    try:
        yield client, factory
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        del app.state.strategy_package_store
        del app.state.strategy_sandbox_factory
        del app.state.agent_rate_limiter
        del app.state.simulation_rate_limiter
        del app.state.match_queue
        engine.dispose()


def send(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    subject: str | None = None,
    key: str | None = None,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    headers: dict[str, str] = {}
    if subject:
        headers["X-Test-Subject"] = subject
    if key:
        headers["Authorization"] = f"Bearer {key}"

    async def request() -> httpx.Response:
        return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(request())


def create_fleet_and_key(
    client: httpx.AsyncClient,
    scopes: list[str],
) -> tuple[str, str, str]:
    fleet = send(
        client,
        "POST",
        "/api/v1/fleets",
        subject="owner",
        json={
            "name": "Key Fleet",
            "commanderCode": "KEY-1",
            "declaration": "",
            "strategyTendency": "balanced",
            "styleDescription": "A graphite spindle with a segmented amber drive halo.",
        },
    )
    public_id = fleet.json()["publicId"]
    issued = send(
        client,
        "POST",
        f"/api/v1/fleets/{public_id}/agent-keys",
        subject="owner",
        json={"scopes": scopes},
    )
    return public_id, issued.json()["key"], issued.json()["publicPrefix"]


def test_key_is_shown_once_hashed_and_authenticates_scoped_fleet(
    agent_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, factory = agent_client
    public_id, credential, prefix = create_fleet_and_key(client, ["fleet:read"])

    fleet = send(client, "GET", "/api/agent/v1/fleet", key=credential)
    wrong = send(client, "GET", "/api/agent/v1/fleet", key=credential + "bad")
    listed = send(client, "GET", f"/api/v1/fleets/{public_id}/agent-keys", subject="owner")
    with factory() as session:
        stored = session.scalar(select(AgentKey).where(AgentKey.public_prefix == prefix))

    assert fleet.status_code == 200
    assert fleet.json()["publicId"] == public_id
    assert wrong.status_code == 401
    assert listed.json()[0]["publicPrefix"] == prefix
    assert "key" not in listed.text
    assert "secretDigest" not in listed.text
    assert stored is not None
    assert credential not in stored.secret_digest
    assert len(stored.secret_digest) == 64


def test_scope_denial_revocation_and_rate_limit_are_stable(agent_client) -> None:
    client, _factory = agent_client
    public_id, credential, prefix = create_fleet_and_key(client, ["fleet:read"])

    forbidden = send(client, "GET", "/api/agent/v1/versions", key=credential)
    revoked = send(
        client,
        "DELETE",
        f"/api/v1/fleets/{public_id}/agent-keys/{prefix}",
        subject="owner",
    )
    after_revoke = send(client, "GET", "/api/agent/v1/fleet", key=credential)

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "agent_key.insufficient_scope"
    assert revoked.status_code == 204
    assert after_revoke.status_code == 401
    assert after_revoke.json()["detail"]["code"] == "agent_key.invalid"

    _other_id, rate_key, _prefix = create_fleet_and_key_for_subject(
        client, "rate-owner", ["fleet:read"]
    )
    app.state.agent_rate_limiter = SlidingWindowLimiter(limit=1)
    assert send(client, "GET", "/api/agent/v1/fleet", key=rate_key).status_code == 200
    limited = send(client, "GET", "/api/agent/v1/fleet", key=rate_key)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def create_fleet_and_key_for_subject(
    client: httpx.AsyncClient,
    subject: str,
    scopes: list[str],
) -> tuple[str, str, str]:
    fleet = send(
        client,
        "POST",
        "/api/v1/fleets",
        subject=subject,
        json={
            "name": f"Fleet {subject}",
            "commanderCode": subject,
            "styleDescription": "An asymmetric silver loop with three quiet engine vanes.",
        },
    )
    public_id = fleet.json()["publicId"]
    issued = send(
        client,
        "POST",
        f"/api/v1/fleets/{public_id}/agent-keys",
        subject=subject,
        json={"scopes": scopes},
    )
    return public_id, issued.json()["key"], issued.json()["publicPrefix"]


def test_agent_can_publish_deduplicated_version_and_read_metadata(agent_client) -> None:
    client, _factory = agent_client
    _public_id, credential, _prefix = create_fleet_and_key(
        client, ["version:write", "version:read", "opponents:read", "matches:read"]
    )
    payload = {
        "packageBase64": base64.b64encode(TRAINING.package_bytes()).decode(),
        "notes": "API candidate",
    }

    first = send(client, "POST", "/api/agent/v1/versions", key=credential, json=payload)
    duplicate = send(client, "POST", "/api/agent/v1/versions", key=credential, json=payload)
    versions = send(client, "GET", "/api/agent/v1/versions", key=credential)
    selected = send(
        client,
        "PATCH",
        f"/api/v1/fleets/{_public_id}/current-strategy",
        subject="owner",
        json={"strategyVersionId": first.json()["publicId"]},
    )
    opponents = send(client, "GET", "/api/agent/v1/opponents", key=credential)
    matches = send(client, "GET", "/api/agent/v1/matches", key=credential)

    assert first.status_code == 201
    assert first.json()["status"] == "ready"
    assert duplicate.status_code == 201
    assert duplicate.json()["deduplicated"] is True
    assert len(versions.json()) == 2  # starter + uploaded candidate
    assert selected.status_code == 200
    assert selected.json()["publicId"] == first.json()["publicId"]
    assert opponents.status_code == 200
    assert matches.json() == []


def test_agent_guide_contains_working_endpoint_and_safe_error_contract() -> None:
    guide = Path("docs/agent-guide.md").read_text()
    assert "/api/agent/v1/versions" in guide
    assert "def agent(obs)" in guide
    assert "agent_key.insufficient_scope" in guide
    assert "ORBIT_AGENT_KEY" in guide


def test_agent_and_owner_simulations_are_idempotent_queryable_and_unrated(agent_client) -> None:
    client, factory = agent_client
    fleet_id, credential, _prefix = create_fleet_and_key(client, ["simulate", "matches:read"])
    payload = {
        "mapId": "orbit-drift-v1",
        "opponentType": "builtin",
        "opponentId": "training-v1",
        "idempotencyKey": "agent-training-001",
    }

    first = send(client, "POST", "/api/agent/v1/simulations", key=credential, json=payload)
    replay = send(client, "POST", "/api/agent/v1/simulations", key=credential, json=payload)
    simulation_id = first.json()["publicId"]
    with factory() as session:
        finish_simulation(
            session,
            simulation_id,
            result={"winnerSlot": 0, "reason": "elimination"},
        )
    queried = send(
        client,
        "GET",
        f"/api/agent/v1/simulations/{simulation_id}",
        key=credential,
    )
    owner = send(
        client,
        "POST",
        f"/api/v1/fleets/{fleet_id}/simulations",
        subject="owner",
        json={
            "opponentType": "builtin",
            "opponentId": "basic-v1",
            "idempotencyKey": "owner-training-001",
        },
    )
    with factory() as session:
        matches = list(session.scalars(select(Match)))
        rating_events = list(session.scalars(select(RatingEvent)))

    assert first.status_code == 201
    assert first.json()["idempotentReplay"] is False
    assert replay.json()["publicId"] == simulation_id
    assert replay.json()["idempotentReplay"] is True
    assert queried.status_code == 200
    assert queried.json()["status"] == "finished"
    assert queried.json()["mapId"] == "orbit-drift-v1"
    assert len(queried.json()["participants"]) == 2
    assert owner.status_code == 201
    assert len(matches) == 2
    assert rating_events == []
    assert len(app.state.match_queue.items) == 2


def test_candidate_simulation_is_validated_queued_and_does_not_publish_version(
    agent_client,
) -> None:
    client, factory = agent_client
    fleet_id, credential, _prefix = create_fleet_and_key(client, ["simulate", "version:read"])
    with factory() as session:
        fleet = session.scalar(select(Fleet).where(Fleet.public_id == fleet_id))
        assert fleet is not None
        current_before = fleet.current_strategy_version_id
        versions_before = len(
            list(
                session.scalars(select(StrategyVersion).where(StrategyVersion.fleet_id == fleet.id))
            )
        )
    response = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={
            "candidatePackageBase64": base64.b64encode(TRAINING.package_bytes()).decode(),
            "candidateNotes": "unpublished inner-loop candidate",
            "submittedBy": "codex-agent",
            "opponentType": "builtin",
            "opponentId": "training-v1",
            "idempotencyKey": "candidate-simulation-001",
        },
    )
    with factory() as session:
        fleet = session.scalar(select(Fleet).where(Fleet.public_id == fleet_id))
        assert fleet is not None
        versions_after = len(
            list(
                session.scalars(select(StrategyVersion).where(StrategyVersion.fleet_id == fleet.id))
            )
        )
        participant = session.scalar(
            select(MatchParticipant)
            .join(Match, Match.id == MatchParticipant.match_id)
            .where(Match.public_id == response.json()["publicId"], MatchParticipant.slot == 0)
        )

    assert response.status_code == 201
    candidate = response.json()["participants"][0]["candidate"]
    assert candidate["submittedBy"] == "codex-agent"
    assert candidate["validation"]["result"] == "ready"
    assert response.json()["participants"][0]["strategyVersionId"] is None
    assert participant is not None and participant.candidate_object_key
    assert participant.candidate_object_key in app.state.strategy_package_store.objects
    assert fleet.current_strategy_version_id == current_before
    assert versions_after == versions_before
    assert response.json()["publicId"] in app.state.match_queue.items


def test_candidate_simulation_rejects_invalid_or_ambiguous_package(agent_client) -> None:
    client, _factory = agent_client
    _fleet_id, credential, _prefix = create_fleet_and_key(client, ["simulate"])
    invalid = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={
            "candidatePackageBase64": base64.b64encode(b"not a zip").decode(),
            "idempotencyKey": "candidate-invalid-001",
        },
    )
    ambiguous = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={
            "candidatePackageBase64": base64.b64encode(TRAINING.package_bytes()).decode(),
            "strategyVersionId": "strategy_existing",
            "idempotencyKey": "candidate-ambiguous-001",
        },
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "strategy.invalid_package"
    assert ambiguous.status_code == 422


def test_simulation_rejects_conflicting_retry_and_limits_by_fleet_and_key(agent_client) -> None:
    client, _factory = agent_client
    _fleet_id, credential, _prefix = create_fleet_and_key(client, ["simulate"])
    base = {
        "opponentType": "builtin",
        "opponentId": "training-v1",
        "idempotencyKey": "same-key",
    }
    assert (
        send(client, "POST", "/api/agent/v1/simulations", key=credential, json=base).status_code
        == 201
    )
    conflict = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={**base, "mapId": "orbit-crown-v1"},
    )
    app.state.simulation_rate_limiter = SlidingWindowLimiter(limit=1)
    allowed = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={**base, "idempotencyKey": "limited"},
    )
    limited = send(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=credential,
        json={**base, "idempotencyKey": "limited-again"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "simulation.idempotency_conflict"
    assert allowed.status_code == 201
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "simulation.rate_limited"


def test_agent_challenge_uses_ranked_rules_and_is_safely_idempotent(agent_client) -> None:
    client, _factory = agent_client
    own_id, credential, _prefix = create_fleet_and_key(client, ["challenge"])
    opponent_id, _key, _prefix = create_fleet_and_key_for_subject(
        client, "challenge-opponent", ["fleet:read"]
    )
    payload = {
        "opponentFleetId": opponent_id,
        "opponentControllerType": "agent",
        "idempotencyKey": "challenge-001",
    }

    first = send(client, "POST", "/api/agent/v1/challenges", key=credential, json=payload)
    replay = send(client, "POST", "/api/agent/v1/challenges", key=credential, json=payload)

    assert first.status_code == 201
    assert first.json()["matchmakingReason"].startswith("direct_challenge")
    assert first.json()["ratingMultiplier"] == 1.0
    assert replay.json()["publicId"] == first.json()["publicId"]
    assert replay.json()["idempotentReplay"] is True
    assert own_id != opponent_id
