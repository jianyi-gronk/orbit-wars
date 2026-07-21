import pytest
from orbit_api.security.credentials import (
    CredentialInputError,
    challenge_digest,
    email_subject,
    generate_verification_code,
    hash_password,
    new_session_token,
    normalize_email,
    request_fingerprint,
    session_digest,
    validate_password,
    verify_password,
)

SECRET = "test-secret-that-is-at-least-thirty-two-bytes-long"


def test_email_and_password_inputs_are_normalized_and_bounded() -> None:
    assert normalize_email(" Pilot@Example.COM ") == "pilot@example.com"
    assert validate_password("correct horse") == "correct horse"

    for value in ("missing-at.example.com", "a@b", f"{'a' * 65}@example.com"):
        with pytest.raises(CredentialInputError) as raised:
            normalize_email(value)
        assert raised.value.code == "invalid_email"

    with pytest.raises(CredentialInputError) as short:
        validate_password("short")
    assert short.value.code == "password_too_short"
    with pytest.raises(CredentialInputError) as long:
        validate_password("x" * 129)
    assert long.value.code == "password_too_long"


def test_scrypt_hash_is_salted_versioned_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first.startswith("scrypt-v1$16384$8$1$")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)
    assert not verify_password("anything", "broken")
    assert not verify_password("anything", first.replace("scrypt-v1", "scrypt-v2", 1))


def test_challenge_and_session_tokens_are_scoped_and_digested() -> None:
    code = generate_verification_code()
    token = new_session_token()

    assert len(code) == 6 and code.isdigit()
    assert len(token) >= 43
    assert challenge_digest(
        SECRET,
        purpose="register",
        email_normalized="pilot@example.com",
        code=code,
    ) != challenge_digest(
        SECRET,
        purpose="password_reset",
        email_normalized="pilot@example.com",
        code=code,
    )
    assert session_digest(SECRET, token) != token
    assert request_fingerprint(SECRET, client_ip="127.0.0.1", user_agent="test") != (
        request_fingerprint(SECRET, client_ip="127.0.0.2", user_agent="test")
    )
    assert email_subject("pilot@example.com").startswith("email:")


def test_digest_helpers_reject_short_secrets() -> None:
    with pytest.raises(ValueError):
        session_digest("too-short", "token")
