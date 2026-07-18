"""Provider-neutral OIDC JWT verification and secure session cookies."""

from dataclasses import dataclass
from os import environ
from typing import Any, Protocol

import jwt
from fastapi import HTTPException, Request, Response, status
from jwt import PyJWKClient

SESSION_COOKIE = "orbit_session"


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    audience: str
    jwks_url: str

    @classmethod
    def from_environment(cls) -> "OIDCSettings":
        issuer = environ.get("OIDC_ISSUER", "").rstrip("/")
        audience = environ.get("OIDC_AUDIENCE", "")
        jwks_url = environ.get("OIDC_JWKS_URL", f"{issuer}/.well-known/jwks.json")
        if not issuer or not audience:
            raise RuntimeError("OIDC_ISSUER and OIDC_AUDIENCE must be configured")
        return cls(issuer=issuer, audience=audience, jwks_url=jwks_url)


@dataclass(frozen=True)
class Principal:
    subject: str
    claims: dict[str, Any]


class SigningKeyProvider(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class OIDCVerifier:
    def __init__(
        self,
        settings: OIDCSettings,
        key_provider: SigningKeyProvider | None = None,
    ) -> None:
        self.settings = settings
        self.key_provider = key_provider or PyJWKClient(settings.jwks_url)

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self.key_provider.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or expired session",
            ) from error

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="session has no subject",
            )
        return Principal(subject=subject, claims=claims)


def bearer_or_cookie_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials:
        return credentials
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


def current_principal(request: Request) -> Principal:
    """FastAPI dependency that uses the verifier configured on app state."""
    dev_subject = request.headers.get("X-Orbit-Dev-Subject")
    dev_auth = environ.get("ORBIT_DEV_AUTH", "").lower() in {"1", "true", "yes"}
    production = environ.get("APP_ENV", "development").lower() in {"production", "prod"}
    if dev_subject and dev_auth and not production:
        return Principal(subject=dev_subject[:255], claims={"name": "Local Commander"})
    verifier = getattr(request.app.state, "oidc_verifier", None)
    if not isinstance(verifier, OIDCVerifier):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC verifier is not configured",
        )
    return verifier.verify(bearer_or_cookie_token(request))


def set_session_cookie(response: Response, token: str, *, secure: bool = True) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
