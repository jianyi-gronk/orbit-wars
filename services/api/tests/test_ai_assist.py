import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from orbit_api.db.base import Base
from orbit_api.db.models import AiCreditAccount, User
from orbit_api.db.session import database_session
from orbit_api.domain.ai_assist import AiProviderResult, AiUnavailableError
from orbit_api.main import app
from orbit_api.security.oidc import Principal, current_principal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


class FakeProvider:
    model = "deepseek-v4-flash"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.user_ids: list[str] = []

    def complete(self, *, source, kind, deep, goal, user_id):
        self.user_ids.append(user_id)
        if self.fail:
            raise AiUnavailableError("offline")
        proposed = source.replace("LAUNCH_RATIO = 0.35", "LAUNCH_RATIO = 0.45")
        return AiProviderResult(
            summary="Increase pressure carefully.",
            reasoning="The starter keeps too much reserve.",
            proposed_source=proposed if kind == "patch" else source,
            tests=("Run the fixed match",),
            input_tokens=120,
            output_tokens=80,
        )


def send(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        return await client.request(
            method,
            path,
            headers={"X-Test-Subject": "owner"},
            **kwargs,
        )

    return asyncio.run(request())


def test_ai_assist_debits_only_success_and_returns_reviewable_diff(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/ai-assist.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    def test_principal(request: Request) -> Principal:
        if not request.headers.get("X-Test-Subject"):
            raise HTTPException(401)
        return Principal(subject="owner", claims={})

    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[current_principal] = test_principal
    provider = FakeProvider()
    app.state.ai_provider = provider
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        fleet = send(
            client,
            "POST",
            "/api/v1/fleets",
            json={
                "name": "AI Fleet",
                "commanderCode": "AI-01",
                "strategyTendency": "balanced",
                "styleDescription": "A silver arc with a blue signal wake.",
            },
        ).json()
        path = f"/api/v1/fleets/{fleet['publicId']}/strategy-lab"
        workspace = send(client, "GET", path).json()

        no_consent = send(
            client,
            "POST",
            f"{path}/ai-assists",
            json={"revision": 1, "kind": "patch", "consent": False},
        )
        assert no_consent.status_code == 422

        success = send(
            client,
            "POST",
            f"{path}/ai-assists",
            json={
                "revision": workspace["draft"]["revision"],
                "kind": "patch",
                "consent": True,
                "goal": "Use a little more pressure",
            },
        )
        assert success.status_code == 201
        assert success.json()["remaining"] == 29
        assert "--- current/main.py" in success.json()["diff"]
        assert "owner" not in provider.user_ids[0]

        app.state.ai_provider = FakeProvider(fail=True)
        failed = send(
            client,
            "POST",
            f"{path}/ai-assists",
            json={"revision": 1, "kind": "explain", "consent": True},
        )
        assert failed.status_code == 503
        with factory() as session:
            user = session.scalar(select(User).where(User.oidc_subject == "owner"))
            assert user is not None
            account = session.get(AiCreditAccount, user.id)
            assert account is not None and account.remaining == 29
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        del app.state.ai_provider
        engine.dispose()
