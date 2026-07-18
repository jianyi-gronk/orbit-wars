import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, Request
from orbit_api.db.base import Base
from orbit_api.db.models import Match, MatchParticipant
from orbit_api.db.session import database_session
from orbit_api.domain.match_tickets import MatchTicketError, MatchTicketService
from orbit_api.infrastructure.match_queue import MemoryMatchQueue
from orbit_api.main import app
from orbit_api.security.oidc import Principal, current_principal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def match_client(tmp_path: Path) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/matches.db", connect_args={"check_same_thread": False}
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

    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    app.state.match_queue = MemoryMatchQueue()
    app.state.match_ticket_service = MatchTicketService("test-match-ticket-secret-value-32")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        yield client, factory
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        del app.state.match_queue
        del app.state.match_ticket_service
        engine.dispose()


def send(client: httpx.AsyncClient, method: str, path: str, subject: str, json=None):
    async def request() -> httpx.Response:
        return await client.request(method, path, headers={"X-Test-Subject": subject}, json=json)

    return asyncio.run(request())


def fleet(client: httpx.AsyncClient, subject: str) -> str:
    response = send(
        client,
        "POST",
        "/api/v1/fleets",
        subject,
        {
            "name": f"Fleet {subject}",
            "commanderCode": subject,
            "styleDescription": "An original graphite ring with amber navigation vanes.",
        },
    )
    assert response.status_code == 201
    return response.json()["publicId"]


def test_training_match_creation_pins_random_slots_controller_versions_queue_and_ticket(
    match_client,
) -> None:
    client, factory = match_client
    own = fleet(client, "alpha")
    opponent = fleet(client, "beta")
    payload = {
        "fleetId": own,
        "opponentFleetId": opponent,
        "mode": "training",
        "controllerType": "human",
        "opponentControllerType": "agent",
        "idempotencyKey": "ranked-001",
    }
    created = send(client, "POST", "/api/v1/matches", "alpha", payload)
    replay = send(client, "POST", "/api/v1/matches", "alpha", payload)
    body = created.json()
    service = app.state.match_ticket_service
    claims = service.verify(
        body["ticket"],
        expected_match_id=body["publicId"],
        expected_slot=body["playerSlot"],
    )
    with pytest.raises(MatchTicketError):
        service.verify(body["ticket"], expected_match_id="match_other")
    with factory() as session:
        match = session.scalar(select(Match).where(Match.public_id == body["publicId"]))
        participants = list(
            session.scalars(
                select(MatchParticipant)
                .where(MatchParticipant.match_id == match.id)
                .order_by(MatchParticipant.slot)
            )
        )

    assert created.status_code == 201
    assert replay.json()["publicId"] == body["publicId"]
    assert replay.json()["idempotentReplay"] is True
    assert body["playerSlot"] in (0, 1)
    assert {participant.slot for participant in participants} == {0, 1}
    human = next(
        participant for participant in participants if participant.controller_type == "human"
    )
    agent = next(
        participant for participant in participants if participant.controller_type == "agent"
    )
    assert human.strategy_version_id is None
    assert agent.strategy_version_id is not None
    assert claims.fleet_id == own
    assert app.state.match_queue.items == [body["publicId"]]


def test_human_control_is_rejected_for_ranked_matches(match_client) -> None:
    client, _factory = match_client
    own = fleet(client, "human-ranked")
    opponent = fleet(client, "agent-ranked")

    rejected = send(
        client,
        "POST",
        "/api/v1/matches",
        "human-ranked",
        {
            "fleetId": own,
            "opponentFleetId": opponent,
            "mode": "ranked",
            "controllerType": "human",
            "opponentControllerType": "agent",
            "idempotencyKey": "human-ranked-001",
        },
    )

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "match.human_training_only"
    assert app.state.match_queue.items == []

    agent_ranked = send(
        client,
        "POST",
        "/api/v1/matches",
        "human-ranked",
        {
            "fleetId": own,
            "opponentFleetId": opponent,
            "mode": "ranked",
            "controllerType": "agent",
            "opponentControllerType": "agent",
            "idempotencyKey": "agent-ranked-001",
        },
    )
    assert agent_ranked.status_code == 201
    assert agent_ranked.json()["mode"] == "ranked"


def test_match_conflicting_retry_is_rejected_and_match_is_visible_only_to_participant(
    match_client,
) -> None:
    client, _factory = match_client
    own = fleet(client, "gamma")
    opponent = fleet(client, "delta")
    outsider = fleet(client, "epsilon")
    del outsider
    payload = {
        "fleetId": own,
        "opponentFleetId": opponent,
        "mode": "training",
        "controllerType": "agent",
        "opponentControllerType": "human",
        "idempotencyKey": "training-001",
    }
    created = send(client, "POST", "/api/v1/matches", "gamma", payload)
    conflict = send(
        client,
        "POST",
        "/api/v1/matches",
        "gamma",
        {**payload, "controllerType": "human"},
    )
    own_read = send(client, "GET", f"/api/v1/matches/{created.json()['publicId']}", "gamma")
    outsider_read = send(client, "GET", f"/api/v1/matches/{created.json()['publicId']}", "epsilon")

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "match.idempotency_conflict"
    assert own_read.status_code == 200
    assert outsider_read.status_code == 404
