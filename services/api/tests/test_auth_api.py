import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from orbit_api.db.base import Base
from orbit_api.db.models import AuthCredential, AuthSession, OAuthIdentity, User
from orbit_api.db.session import database_session
from orbit_api.main import app
from orbit_api.security.auth_settings import AuthSettings, get_auth_settings
from orbit_api.security.github_oauth import GitHubProfile
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

SECRET = "test-secret-that-is-at-least-thirty-two-bytes-long"
SETTINGS = AuthSettings(
    enabled=True,
    secret=SECRET,
    public_base_url="http://test",
    cookie_secure=False,
    debug_codes=True,
    password_enabled=True,
)


@pytest.fixture
def auth_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/auth.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    monkeypatch.setenv("ORBIT_AUTH_SECRET", SECRET)
    monkeypatch.setenv("APP_ENV", "test")
    app.dependency_overrides[database_session] = test_session
    app.dependency_overrides[get_auth_settings] = lambda: SETTINGS
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    try:
        yield client, factory
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        engine.dispose()


def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async def send() -> httpx.Response:
        return await client.request(method, path, json=json, headers=headers)

    return asyncio.run(send())


def register(client: httpx.AsyncClient, email: str = "pilot@example.com") -> str:
    challenge = request(
        client,
        "POST",
        "/api/auth/register/request",
        json={"email": email, "locale": "zh"},
    )
    assert challenge.status_code == 202
    code = challenge.json()["debugCode"]
    completed = request(
        client,
        "POST",
        "/api/auth/register/complete",
        json={
            "email": email,
            "code": code,
            "password": "initial-password",
            "displayName": "Orbit Pilot",
        },
    )
    assert completed.status_code == 201
    return code


def test_registration_session_logout_and_login(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    config = request(client, "GET", "/api/auth/config")
    assert config.json() == {
        "enabled": True,
        "passwordEnabled": True,
        "providers": {"github": False, "google": False},
    }
    assert request(client, "GET", "/api/auth/session").json() == {"authenticated": False}

    register(client)
    public_session = request(client, "GET", "/api/auth/session")
    assert public_session.json()["email"] == "pilot@example.com"
    session = request(client, "GET", "/api/v1/session")
    assert session.status_code == 200
    assert session.json()["displayName"] == "Orbit Pilot"

    logged_out = request(client, "POST", "/api/auth/logout")
    assert logged_out.status_code == 204
    assert request(client, "GET", "/api/v1/session").status_code == 401

    invalid = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "pilot@example.com", "password": "wrong-password"},
    )
    logged_in = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "PILOT@example.com", "password": "initial-password"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "auth.invalid_credentials"
    assert logged_in.status_code == 200
    assert "HttpOnly" in logged_in.headers["set-cookie"]
    assert logged_in.json()["email"] == "pilot@example.com"


def test_registration_code_is_single_use_and_rate_limited(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    code = register(client, "single@example.com")
    reused = request(
        client,
        "POST",
        "/api/auth/register/complete",
        json={
            "email": "another@example.com",
            "code": code,
            "password": "another-password",
            "displayName": "Another Pilot",
        },
    )
    duplicate_request = request(
        client,
        "POST",
        "/api/auth/register/request",
        json={"email": "single@example.com", "locale": "en"},
    )
    assert reused.status_code == 400
    assert duplicate_request.status_code == 409

    first = request(
        client,
        "POST",
        "/api/auth/register/request",
        json={"email": "cooldown@example.com", "locale": "en"},
    )
    second = request(
        client,
        "POST",
        "/api/auth/register/request",
        json={"email": "cooldown@example.com", "locale": "en"},
    )
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "auth.code_cooldown"


def test_password_reset_revokes_existing_sessions(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, factory = auth_client
    register(client, "reset@example.com")
    old_cookie = client.cookies.get("orbit_session")
    challenge = request(
        client,
        "POST",
        "/api/auth/password/request",
        json={"email": "reset@example.com", "locale": "zh"},
    )
    reset = request(
        client,
        "POST",
        "/api/auth/password/reset",
        json={
            "email": "reset@example.com",
            "code": challenge.json()["debugCode"],
            "password": "replacement-password",
        },
    )
    assert reset.status_code == 200
    assert client.cookies.get("orbit_session") != old_cookie

    with factory() as db:
        sessions = list(db.scalars(select(AuthSession).order_by(AuthSession.created_at)))
        assert len(sessions) == 2
        assert sessions[0].revoked_at is not None
        assert sessions[1].revoked_at is None
        credential = db.scalar(
            select(AuthCredential).where(AuthCredential.email_normalized == "reset@example.com")
        )
        assert credential is not None
        assert credential.failed_attempts == 0

    request(client, "POST", "/api/auth/logout")
    old_password = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "initial-password"},
    )
    new_password = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "reset@example.com", "password": "replacement-password"},
    )
    assert old_password.status_code == 401
    assert new_password.status_code == 200


def test_login_locks_after_five_failures(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    register(client, "locked@example.com")
    request(client, "POST", "/api/auth/logout")

    failures = [
        request(
            client,
            "POST",
            "/api/auth/login",
            json={"email": "locked@example.com", "password": "wrong-password"},
        )
        for _ in range(5)
    ]
    locked = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "locked@example.com", "password": "initial-password"},
    )
    assert all(response.status_code == 401 for response in failures)
    assert locked.status_code == 429
    assert locked.json()["detail"]["code"] == "auth.account_locked"


def test_disabled_auth_config_and_routes(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    disabled = AuthSettings(
        enabled=False,
        secret="",
        public_base_url="http://test",
        cookie_secure=False,
        debug_codes=False,
    )
    app.dependency_overrides[get_auth_settings] = lambda: disabled

    assert request(client, "GET", "/api/auth/config").json()["enabled"] is False
    unavailable = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "pilot@example.com", "password": "initial-password"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "auth.unavailable"


def test_github_oauth_creates_and_reuses_one_identity(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = auth_client
    github_settings = AuthSettings(
        enabled=True,
        secret=SECRET,
        public_base_url="http://test",
        cookie_secure=False,
        debug_codes=False,
        github_enabled=True,
        github_client_id="github-client",
        github_client_secret="github-secret",
        github_redirect_uri="http://test/orbit-api/api/auth/github/callback",
    )
    app.dependency_overrides[get_auth_settings] = lambda: github_settings
    monkeypatch.setattr(
        "orbit_api.api.auth.exchange_github_code",
        lambda _settings, _code: GitHubProfile(
            subject="4242",
            display_name="GitHub Pilot",
            email="pilot@users.noreply.github.com",
            avatar_url="https://avatars.example/4242",
        ),
    )

    start = request(client, "GET", "/api/auth/github/start?returnTo=/zh/start")
    assert start.status_code == 307
    assert start.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    state = client.cookies.get("orbit_oauth_state")
    assert state

    callback = request(
        client,
        "GET",
        f"/api/auth/github/callback?code=github-code&state={state}",
    )
    assert callback.status_code == 307
    assert callback.headers["location"] == "/zh/start"
    assert client.cookies.get("orbit_session")

    with factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(OAuthIdentity.id))) == 1
        assert db.scalar(select(func.count(AuthSession.id))) == 1
        identity = db.scalar(select(OAuthIdentity))
        assert identity is not None
        assert identity.provider == "github"
        assert identity.provider_subject == "4242"

    client.cookies.clear()
    second_start = request(client, "GET", "/api/auth/github/start?returnTo=//evil.example")
    second_state = client.cookies.get("orbit_oauth_state")
    assert second_start.status_code == 307
    second_callback = request(
        client,
        "GET",
        f"/api/auth/github/callback?code=github-code-2&state={second_state}",
    )
    assert second_callback.headers["location"] == "/zh/command"
    with factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(OAuthIdentity.id))) == 1
        assert db.scalar(select(func.count(AuthSession.id))) == 2


def test_github_callback_rejects_state_mismatch(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    github_settings = AuthSettings(
        enabled=True,
        secret=SECRET,
        public_base_url="http://test",
        cookie_secure=False,
        debug_codes=False,
        github_enabled=True,
        github_client_id="github-client",
        github_client_secret="github-secret",
        github_redirect_uri="http://test/orbit-api/api/auth/github/callback",
    )
    app.dependency_overrides[get_auth_settings] = lambda: github_settings
    request(client, "GET", "/api/auth/github/start?returnTo=/zh/start")
    callback = request(
        client,
        "GET",
        "/api/auth/github/callback?code=github-code&state=wrong-state",
    )
    assert callback.status_code == 307
    assert callback.headers["location"] == "/zh/start?auth=invalid"


def test_auth_writes_reject_cross_origin_browser_requests(
    auth_client: tuple[httpx.AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = auth_client
    response = request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "pilot@example.com", "password": "initial-password"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "auth.invalid_origin"
