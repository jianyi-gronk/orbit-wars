import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException, Response
from orbit_api.db.base import Base
from orbit_api.db.models import IdempotencyRecord
from orbit_api.middleware.idempotency import IdempotencyMiddleware, request_digest, reserve
from orbit_api.security.oidc import OIDCSettings, OIDCVerifier, set_session_cookie
from orbit_api.security.public_ids import new_public_id
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def test_core_metadata_contains_phase_one_tables() -> None:
    assert {
        "users",
        "fleets",
        "agent_keys",
        "strategy_versions",
        "matches",
        "match_participants",
        "match_commands",
        "ratings",
        "rating_events",
        "replay_artifacts",
        "idempotency_records",
    } <= set(Base.metadata.tables)


def test_public_ids_are_prefixed_random_and_not_uuid_values() -> None:
    first = new_public_id("fleet")
    second = new_public_id("fleet")

    assert first.startswith("fleet_")
    assert first != second
    assert len(first) > 25


def test_idempotency_reservation_replays_and_detects_conflicts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    IdempotencyRecord.__table__.create(engine)
    digest = request_digest("POST", "/fleets", b'{"name":"A"}')

    with Session(engine, expire_on_commit=False) as session:
        first = reserve(
            session,
            scope="user:1",
            key="create-fleet-1",
            method="POST",
            path="/fleets",
            digest=digest,
        )
        assert first.state == "reserved"
        first.record.response_status = 201
        first.record.response_body = {"publicId": "fleet_123"}
        session.commit()

        replay = reserve(
            session,
            scope="user:1",
            key="create-fleet-1",
            method="POST",
            path="/fleets",
            digest=digest,
        )
        conflict = reserve(
            session,
            scope="user:1",
            key="create-fleet-1",
            method="POST",
            path="/fleets",
            digest=request_digest("POST", "/fleets", b'{"name":"B"}'),
        )

    assert replay.state == "replay"
    assert replay.record.response_body == {"publicId": "fleet_123"}
    assert conflict.state == "conflict"


def test_idempotency_middleware_replays_business_response(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/idempotency.db")
    IdempotencyRecord.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    test_app = FastAPI()
    test_app.add_middleware(IdempotencyMiddleware, session_factory=session_factory)
    calls = 0

    @test_app.post("/write")
    def write(payload: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"call": calls, "payload": payload}

    async def exercise() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/write",
                json={"name": "alpha"},
                headers={"Idempotency-Key": "write-alpha-1"},
            )
            replay = await client.post(
                "/write",
                json={"name": "alpha"},
                headers={"Idempotency-Key": "write-alpha-1"},
            )
            conflict = await client.post(
                "/write",
                json={"name": "beta"},
                headers={"Idempotency-Key": "write-alpha-1"},
            )
        return first, replay, conflict

    first, replay, conflict = asyncio.run(exercise())

    assert first.json() == {"call": 1, "payload": {"name": "alpha"}}
    assert replay.json() == first.json()
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert conflict.status_code == 409
    assert calls == 1


def test_oidc_verifier_requires_issuer_audience_and_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = OIDCSettings(
        issuer="https://identity.example",
        audience="orbit-wars",
        jwks_url="https://identity.example/jwks.json",
    )
    key_provider = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key="public-key")
    )
    verifier = OIDCVerifier(settings, key_provider)
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda *_args, **_kwargs: {"sub": "user-123", "iat": 1, "exp": 2},
    )

    assert verifier.verify("signed-token").subject == "user-123"

    monkeypatch.setattr(jwt, "decode", lambda *_args, **_kwargs: {"iat": 1, "exp": 2})
    with pytest.raises(HTTPException) as raised:
        verifier.verify("signed-token")
    assert raised.value.status_code == 401


def test_session_cookie_is_http_only_secure_and_same_site() -> None:
    response = Response()
    set_session_cookie(response, "signed-token")
    cookie = response.headers["set-cookie"]

    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
