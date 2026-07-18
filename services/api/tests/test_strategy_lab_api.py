import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from orbit_api.db.base import Base
from orbit_api.db.models import Match, MatchParticipant, RatingEvent, StrategyDraft
from orbit_api.db.session import database_session
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


def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    subject: str,
    **kwargs,
) -> httpx.Response:
    async def send() -> httpx.Response:
        return await client.request(
            method,
            path,
            headers={"X-Test-Subject": subject},
            **kwargs,
        )

    return asyncio.run(send())


def create_fleet(client: httpx.AsyncClient, subject: str = "owner") -> str:
    response = request(
        client,
        "POST",
        "/api/v1/fleets",
        subject,
        json={
            "name": "Lab Fleet",
            "commanderCode": "LAB-01",
            "strategyTendency": "balanced",
            "styleDescription": "A cobalt ring ship with an amber wake.",
        },
    )
    assert response.status_code == 201
    return str(response.json()["publicId"])


def test_workspace_draft_simulation_and_publish_flow(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/strategy-lab.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def test_principal(request_value: Request) -> Principal:
        subject = request_value.headers.get("X-Test-Subject")
        if not subject:
            raise HTTPException(401)
        return Principal(subject=subject, claims={})

    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    app.state.strategy_package_store = MemoryStore()
    app.state.strategy_sandbox_factory = LocalSandboxSession
    app.state.match_queue = MemoryMatchQueue()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        fleet_id = create_fleet(client)
        workspace = request(
            client,
            "GET",
            f"/api/v1/fleets/{fleet_id}/strategy-lab",
            "owner",
        )
        assert workspace.status_code == 200
        assert workspace.json()["draft"]["revision"] == 1
        assert workspace.json()["aiCredits"] == {
            "remaining": 30,
            "granted": 30,
            "standardCost": 1,
            "deepCost": 2,
        }

        saved = request(
            client,
            "PUT",
            f"/api/v1/fleets/{fleet_id}/strategy-lab/draft",
            "owner",
            json={
                "expectedRevision": 1,
                "mode": "guided",
                "parameters": {
                    "launchRatio": 0.5,
                    "minimumShips": 6,
                    "targetPreference": "weakest",
                },
            },
        )
        assert saved.status_code == 200
        assert saved.json()["draft"]["revision"] == 2
        assert "LAUNCH_RATIO = 0.50" in saved.json()["draft"]["sourceCode"]

        stale = request(
            client,
            "PUT",
            f"/api/v1/fleets/{fleet_id}/strategy-lab/draft",
            "owner",
            json={"expectedRevision": 1, "mode": "code", "sourceCode": "def agent(obs): return []"},
        )
        assert stale.status_code == 409

        simulated = request(
            client,
            "POST",
            f"/api/v1/fleets/{fleet_id}/strategy-lab/simulations",
            "owner",
            json={"revision": 2, "idempotencyKey": "lab-simulation-1"},
        )
        assert simulated.status_code == 201
        assert simulated.json()["participants"][0]["candidate"]["validation"]["result"] == "ready"

        published = request(
            client,
            "POST",
            f"/api/v1/fleets/{fleet_id}/strategy-lab/publish",
            "owner",
            json={"revision": 2, "notes": "Weakest target test", "makeCurrent": True},
        )
        assert published.status_code == 201
        assert published.json()["status"] == "ready"
        with factory() as session:
            draft = session.scalar(select(StrategyDraft))
            match = session.scalar(
                select(Match).where(Match.public_id == simulated.json()["publicId"])
            )
            assert match is not None
            participant = session.scalar(
                select(MatchParticipant).where(MatchParticipant.match_id == match.id)
            )
            assert draft is not None and draft.validated_content_hash
            assert participant is not None and participant.candidate_content_hash
            assert session.scalar(select(RatingEvent)) is None

        private = request(
            client,
            "GET",
            f"/api/v1/fleets/{fleet_id}/strategy-lab",
            "other",
        )
        assert private.status_code == 404
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        for attribute in ("strategy_package_store", "strategy_sandbox_factory", "match_queue"):
            delattr(app.state, attribute)
        engine.dispose()
