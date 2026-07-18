import asyncio
import base64
import gzip
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, Request
from orbit_api.api.agent import SlidingWindowLimiter
from orbit_api.builtin_strategies.registry import TRAINING
from orbit_api.db.base import Base
from orbit_api.db.models import Match, MatchStatus, ReplayArtifact
from orbit_api.db.session import database_session
from orbit_api.domain.match_tickets import MatchTicketService
from orbit_api.domain.ratings import RatingService
from orbit_api.domain.strategy_validation import LocalSandboxSession
from orbit_api.infrastructure.match_queue import MemoryMatchQueue
from orbit_api.main import app
from orbit_api.security.oidc import Principal, current_principal
from orbit_api.storage.strategy_packages import StoredPackage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


class JourneyStore:
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

    def signed_url(self, key: str, *, expires_seconds: int = 300) -> None:
        del key, expires_seconds
        return None


@pytest.fixture
def journey(
    tmp_path: Path,
) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session], JourneyStore]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/journey.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def test_principal(request: Request) -> Principal:
        subject = request.headers.get("X-Test-Subject")
        if not subject:
            raise HTTPException(401)
        return Principal(subject, {})

    store = JourneyStore()
    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    app.state.strategy_package_store = store
    app.state.strategy_sandbox_factory = LocalSandboxSession
    app.state.replay_store = store
    app.state.match_queue = MemoryMatchQueue()
    app.state.match_ticket_service = MatchTicketService("journey-match-ticket-secret-value-32")
    app.state.agent_rate_limiter = SlidingWindowLimiter(limit=100)
    app.state.simulation_rate_limiter = SlidingWindowLimiter(limit=100)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        yield client, factory, store
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        for name in (
            "strategy_package_store",
            "strategy_sandbox_factory",
            "replay_store",
            "match_queue",
            "match_ticket_service",
            "agent_rate_limiter",
            "simulation_rate_limiter",
        ):
            delattr(app.state, name)
        engine.dispose()


def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    subject: str | None = None,
    key: str | None = None,
    json_body: dict[str, object] | None = None,
) -> httpx.Response:
    headers = {}
    if subject:
        headers["X-Test-Subject"] = subject
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return asyncio.run(client.request(method, path, headers=headers, json=json_body))


def create_fleet(client: httpx.AsyncClient, subject: str) -> str:
    response = request(
        client,
        "POST",
        "/api/v1/fleets",
        subject=subject,
        json_body={
            "name": f"Journey {subject}",
            "commanderCode": subject,
            "styleDescription": "An original graphite orbital lattice with amber fins.",
        },
    )
    assert response.status_code == 201
    return response.json()["publicId"]


def test_three_clean_environment_product_loops(journey) -> None:
    client, factory, store = journey
    own = create_fleet(client, "journey-owner")
    opponent = create_fleet(client, "journey-opponent")

    # Loop 1: create -> manual training.
    manual = request(
        client,
        "POST",
        "/api/v1/matches",
        subject="journey-owner",
        json_body={
            "fleetId": own,
            "opponentFleetId": opponent,
            "mode": "training",
            "controllerType": "human",
            "opponentControllerType": "agent",
            "idempotencyKey": "journey-manual-001",
        },
    )
    assert manual.status_code == 201
    assert {item["controllerType"] for item in manual.json()["participants"]} == {
        "human",
        "agent",
    }

    # Loop 2: create -> scoped Agent publish -> simulation.
    issued = request(
        client,
        "POST",
        f"/api/v1/fleets/{own}/agent-keys",
        subject="journey-owner",
        json_body={"scopes": ["version:write", "simulate", "challenge"]},
    )
    key = issued.json()["key"]
    published = request(
        client,
        "POST",
        "/api/agent/v1/versions",
        key=key,
        json_body={
            "packageBase64": base64.b64encode(TRAINING.package_bytes()).decode(),
            "notes": "Journey candidate",
        },
    )
    simulation = request(
        client,
        "POST",
        "/api/agent/v1/simulations",
        key=key,
        json_body={
            "opponentType": "builtin",
            "opponentId": "training-v1",
            "strategyVersionId": published.json()["publicId"],
            "idempotencyKey": "journey-simulation-001",
        },
    )
    assert published.status_code == 201 and published.json()["status"] == "ready"
    assert simulation.status_code == 201 and simulation.json()["mode"] == "training"
    selected = request(
        client,
        "PATCH",
        f"/api/v1/fleets/{own}/current-strategy",
        subject="journey-owner",
        json_body={"strategyVersionId": published.json()["publicId"]},
    )
    assert selected.status_code == 200

    # Loop 3: unified ranked result -> rating -> permanent replay -> public profile.
    ranked = request(
        client,
        "POST",
        "/api/v1/matches",
        subject="journey-owner",
        json_body={
            "fleetId": own,
            "opponentFleetId": opponent,
            "mode": "ranked",
            "controllerType": "agent",
            "opponentControllerType": "agent",
            "idempotencyKey": "journey-ranked-001",
        },
    )
    records = [
        {"type": "checkpoint", "frame": {"step": 0, "planets": [], "fleets": []}},
        {"type": "result", "result": {"winnerSlot": ranked.json()["playerSlot"]}},
    ]
    content = gzip.compress(("\n".join(json.dumps(item) for item in records) + "\n").encode())
    with factory() as session:
        match = session.scalar(select(Match).where(Match.public_id == ranked.json()["publicId"]))
        artifact = ReplayArtifact(
            object_key="replays/journey.jsonl.gz",
            schema_version=1,
            checksum=hashlib.sha256(content).hexdigest(),
            metadata_payload={"participants": ranked.json()["participants"]},
            analysis_payload={"events": [{"type": "match_finished", "step": 0}]},
            size_bytes=len(content),
            frame_count=1,
            is_public=True,
        )
        session.add(artifact)
        session.flush()
        match.replay_id = artifact.id
        match.status = MatchStatus.FINISHED
        match.result = {
            "winnerSlot": ranked.json()["playerSlot"],
            "reason": "elimination",
            "finalStep": 0,
        }
        session.commit()
        RatingService().apply_once(session, match.id)
        replay_id = artifact.public_id
    store.objects["replays/journey.jsonl.gz"] = content

    profile = request(client, "GET", f"/api/public/v1/fleet-profiles/{own}")
    replay = request(client, "GET", f"/api/public/v1/replays/{replay_id}")
    assert ranked.status_code == 201
    assert profile.status_code == 200
    assert profile.json()["matches"][0]["controllerType"] == "agent"
    assert profile.json()["matches"][0]["strategyVersionId"] == published.json()["publicId"]
    assert profile.json()["matches"][0]["ratingChange"] is not None
    assert profile.json()["representativeReplayPublicId"] == replay_id
    assert replay.status_code == 200 and replay.json()["matchPublicId"] == ranked.json()["publicId"]
