"""First-party credential, challenge, and opaque-session primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

SCRYPT_N = 16_384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_MAXMEM = 64 * 1024 * 1024
PASSWORD_FORMAT = "scrypt-v1"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CredentialInputError(ValueError):
    """A stable validation failure suitable for translation at the API edge."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise CredentialInputError("invalid_email")
    local, domain = normalized.rsplit("@", 1)
    if len(local) > 64 or any(len(label) > 63 for label in domain.split(".")):
        raise CredentialInputError("invalid_email")
    return normalized


def validate_password(value: str) -> str:
    if len(value) < 8:
        raise CredentialInputError("password_too_short")
    if len(value) > 128:
        raise CredentialInputError("password_too_long")
    return value


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return "$".join(
        (
            PASSWORD_FORMAT,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _encode(salt),
            _encode(derived),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n_text, r_text, p_text, salt_text, digest_text = encoded.split("$")
        n, r, p = int(n_text), int(r_text), int(p_text)
        if scheme != PASSWORD_FORMAT or (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        expected = _decode(digest_text)
        if len(expected) != SCRYPT_DKLEN:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt_text),
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _secret_bytes(secret: str | bytes) -> bytes:
    result = secret.encode("utf-8") if isinstance(secret, str) else secret
    if len(result) < 32:
        raise ValueError("auth secret must contain at least 32 bytes")
    return result


def _hmac_digest(secret: str | bytes, namespace: str, *parts: str) -> str:
    payload = "\0".join((namespace, *parts)).encode("utf-8")
    return hmac.new(_secret_bytes(secret), payload, hashlib.sha256).hexdigest()


def challenge_digest(
    secret: str | bytes,
    *,
    purpose: str,
    email_normalized: str,
    code: str,
) -> str:
    return _hmac_digest(secret, "challenge-v1", purpose, email_normalized, code)


def request_fingerprint(secret: str | bytes, *, client_ip: str, user_agent: str) -> str:
    return _hmac_digest(secret, "request-v1", client_ip, user_agent)


def new_session_token() -> str:
    return _encode(secrets.token_bytes(32))


def session_digest(secret: str | bytes, token: str) -> str:
    return _hmac_digest(secret, "session-v1", token)


def email_subject(email_normalized: str) -> str:
    digest = hashlib.sha256(email_normalized.encode("utf-8")).hexdigest()
    return f"email:{digest}"
