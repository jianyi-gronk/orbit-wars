from types import SimpleNamespace

import pytest
from orbit_api.security.auth_settings import AuthSettings
from orbit_api.security.github_oauth import GitHubOAuthError, exchange_github_code


def settings() -> AuthSettings:
    return AuthSettings(
        enabled=True,
        secret="test-secret-that-is-at-least-thirty-two-bytes-long",
        public_base_url="https://orbit.example",
        cookie_secure=True,
        debug_codes=False,
        github_enabled=True,
        github_client_id="client-id",
        github_client_secret="client-secret",
        github_redirect_uri="https://orbit.example/orbit-api/api/auth/github/callback",
    )


def test_github_exchange_uses_verified_primary_email(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"access_token": "github-token"},
        )

    def get(url: str, **_kwargs: object) -> SimpleNamespace:
        payload: object
        if url.endswith("/user"):
            payload = {
                "id": 42,
                "login": "orbit-pilot",
                "name": "Orbit Pilot",
                "email": None,
                "avatar_url": "https://avatars.example/42",
            }
        else:
            payload = [
                {"email": "other@example.com", "verified": True, "primary": False},
                {"email": "pilot@example.com", "verified": True, "primary": True},
            ]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr("orbit_api.security.github_oauth.httpx.post", post)
    monkeypatch.setattr("orbit_api.security.github_oauth.httpx.get", get)
    profile = exchange_github_code(settings(), "oauth-code")

    assert profile.subject == "42"
    assert profile.display_name == "Orbit Pilot"
    assert profile.email == "pilot@example.com"


def test_github_exchange_rejects_incomplete_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "orbit_api.security.github_oauth.httpx.post",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"access_token": "github-token"},
        ),
    )
    monkeypatch.setattr(
        "orbit_api.security.github_oauth.httpx.get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"login": "missing-id"},
        ),
    )
    with pytest.raises(GitHubOAuthError):
        exchange_github_code(settings(), "oauth-code")
