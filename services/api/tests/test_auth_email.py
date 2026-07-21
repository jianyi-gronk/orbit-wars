from types import SimpleNamespace

import pytest
from orbit_api.security.auth_settings import AuthSettings
from orbit_api.security.email_delivery import EmailDeliveryError, send_verification_email


def settings(*, debug: bool = False) -> AuthSettings:
    return AuthSettings(
        enabled=True,
        secret="test-secret-that-is-at-least-thirty-two-bytes-long",
        public_base_url="https://orbit.example",
        cookie_secure=True,
        debug_codes=debug,
        resend_api_key="resend-key",
        email_from="Orbit Wars <pilot@orbit.example>",
    )


def test_verification_email_has_bilingual_registration_and_reset_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[dict[str, object]] = []

    def post(*_args: object, **kwargs: object) -> SimpleNamespace:
        payloads.append(kwargs["json"])  # type: ignore[arg-type]
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr("orbit_api.security.email_delivery.httpx.post", post)
    send_verification_email(
        settings(),
        email="pilot@example.com",
        code="123456",
        purpose="register",
        locale="zh",
    )
    send_verification_email(
        settings(),
        email="pilot@example.com",
        code="654321",
        purpose="password_reset",
        locale="en",
    )

    assert "完成注册" in str(payloads[0]["text"])
    assert "123456" in str(payloads[0]["text"])
    assert "reset your password" in str(payloads[1]["text"])
    assert "654321" in str(payloads[1]["text"])


def test_debug_email_delivery_is_local_only_and_provider_failures_are_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def post(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1

        def fail() -> None:
            import httpx

            raise httpx.HTTPError("provider unavailable")

        return SimpleNamespace(raise_for_status=fail)

    monkeypatch.setattr("orbit_api.security.email_delivery.httpx.post", post)
    send_verification_email(
        settings(debug=True),
        email="pilot@example.com",
        code="123456",
        purpose="register",
        locale="zh",
    )
    assert calls == 0

    with pytest.raises(EmailDeliveryError):
        send_verification_email(
            settings(),
            email="pilot@example.com",
            code="123456",
            purpose="register",
            locale="en",
        )
