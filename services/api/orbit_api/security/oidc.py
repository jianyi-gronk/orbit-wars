"""First-party sessions, provider-neutral OIDC verification, and cookies."""

from dataclasses import dataclass
from datetime import timedelta
from os import environ
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from jwt import PyJWKClient
from orbit_api.db.base import utc_now
from orbit_api.db.models import AuthCredential, AuthSession, OAuthIdentity, User
from orbit_api.db.session import database_session
from orbit_api.security.credentials import session_digest
from sqlalchemy import select
from sqlalchemy.orm import Session

SESSION_COOKIE = "orbit_session"
SESSION_TTL = timedelta(days=30)


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


def principal_from_session(
    session: Session,
    token: str,
    secret: str | bytes,
) -> Principal | None:
    """Resolve an active opaque session without exposing its stored digest."""
    now = utc_now()
    row = session.execute(
        select(User, AuthCredential.email_normalized, OAuthIdentity.email)
        .join(AuthSession, AuthSession.user_id == User.id)
        .outerjoin(AuthCredential, AuthCredential.user_id == User.id)
        .outerjoin(OAuthIdentity, OAuthIdentity.user_id == User.id)
        .where(
            AuthSession.token_digest == session_digest(secret, token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    ).first()
    if row is None:
        return None
    user, credential_email, oauth_email = row
    email = credential_email or oauth_email
    claims: dict[str, Any] = {"name": user.display_name}
    if email:
        claims["email"] = email
    return Principal(subject=user.oidc_subject, claims=claims)


def current_principal(
    request: Request,
    session: Annotated[Session, Depends(database_session)],
) -> Principal:
    """Resolve dev, first-party, or migration OIDC credentials in that order."""
    dev_subject = request.headers.get("X-Orbit-Dev-Subject")
    dev_auth = environ.get("ORBIT_DEV_AUTH", "").lower() in {"1", "true", "yes"}
    production = environ.get("APP_ENV", "development").lower() in {"production", "prod"}
    if dev_subject and dev_auth and not production:
        return Principal(subject=dev_subject[:255], claims={"name": "Local Commander"})

    cookie = request.cookies.get(SESSION_COOKIE)
    auth_secret = environ.get("ORBIT_AUTH_SECRET", "")
    if cookie and auth_secret:
        try:
            principal = principal_from_session(session, cookie, auth_secret)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication secret is invalid",
            ) from error
        if principal is not None:
            return principal

    authorization = request.headers.get("Authorization", "")
    scheme, _, bearer = authorization.partition(" ")
    migration_token = bearer if scheme.lower() == "bearer" and bearer else cookie
    if not migration_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    verifier = getattr(request.app.state, "oidc_verifier", None)
    if not isinstance(verifier, OIDCVerifier):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired session",
        )
    return verifier.verify(migration_token)


def set_session_cookie(response: Response, token: str, *, secure: bool = True) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=int(SESSION_TTL.total_seconds()),
    )
