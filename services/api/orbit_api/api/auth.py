"""First-party email registration, login, password reset, and logout routes."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import (
    AuthChallenge,
    AuthCredential,
    AuthSession,
    OAuthIdentity,
    User,
)
from orbit_api.db.session import database_session
from orbit_api.security.auth_settings import AuthSettings, get_auth_settings
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
from orbit_api.security.email_delivery import EmailDeliveryError, send_verification_email
from orbit_api.security.github_oauth import GitHubOAuthError, exchange_github_code
from orbit_api.security.oidc import (
    SESSION_COOKIE,
    SESSION_TTL,
    current_principal,
    set_session_cookie,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SessionDependency = Annotated[Session, Depends(database_session)]
SettingsDependency = Annotated[AuthSettings, Depends(get_auth_settings)]
Purpose = Literal["register", "password_reset"]
Locale = Literal["zh", "en"]

CHALLENGE_TTL = timedelta(minutes=10)
CHALLENGE_COOLDOWN = timedelta(seconds=60)
CHALLENGE_WINDOW = timedelta(minutes=15)
CHALLENGE_WINDOW_LIMIT = 5
CHALLENGE_MAX_ATTEMPTS = 5
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_TIME = timedelta(minutes=15)
OAUTH_STATE_COOKIE = "orbit_oauth_state"
OAUTH_RETURN_COOKIE = "orbit_oauth_return"
DUMMY_PASSWORD_HASH = (
    "scrypt-v1$16384$8$1$4XyTw7AqPtG5n52Wo6gTbg$"
    "bYQw8ZiaMJt5aN5E11xDyxKbdUnlVo_7gzw2sUr4ZdxPPYjKxpuFN79aVcphotwTBrImbTpDGYiiCgcyVsL1kA"
)


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
        extra="forbid",
    )


class ChallengeRequest(APIModel):
    email: str
    locale: Locale = "zh"


class RegistrationRequest(APIModel):
    email: str
    code: str
    password: str
    display_name: str


class LoginRequest(APIModel):
    email: str
    password: str


class PasswordResetRequest(APIModel):
    email: str
    code: str
    password: str


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _require_enabled(settings: AuthSettings) -> None:
    if not settings.enabled:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.unavailable")


def _require_password_enabled(settings: AuthSettings) -> None:
    _require_enabled(settings)
    if not settings.password_enabled:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.password_unavailable")


def _require_github_enabled(settings: AuthSettings) -> None:
    _require_enabled(settings)
    if not settings.github_enabled:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.github_unavailable")


def _safe_return_to(value: str | None) -> str:
    return (
        value
        if value and len(value) <= 1024 and value.startswith("/") and not value.startswith("//")
        else "/zh/command"
    )


def _auth_result_url(return_to: str, result: str) -> str:
    separator = "&" if "?" in return_to else "?"
    return f"{return_to}{separator}auth={result}"


def _validate_origin(request: Request, settings: AuthSettings) -> None:
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != settings.public_base_url.rstrip("/"):
        raise _error(status.HTTP_403_FORBIDDEN, "auth.invalid_origin")


def _validated_email(value: str) -> str:
    try:
        return normalize_email(value)
    except CredentialInputError as error:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, f"auth.{error.code}") from error


def _validated_password(value: str) -> str:
    try:
        return validate_password(value)
    except CredentialInputError as error:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, f"auth.{error.code}") from error


def _normalized_display_name(value: str) -> str:
    result = " ".join(value.strip().split())
    if not 2 <= len(result) <= 40:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "auth.invalid_display_name")
    return result


def _client_fingerprint(request: Request, settings: AuthSettings) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    client_ip = forwarded or (request.client.host if request.client else "unknown")
    return request_fingerprint(
        settings.secret,
        client_ip=client_ip,
        user_agent=request.headers.get("User-Agent", "")[:512],
    )


def _check_challenge_rate_limit(
    db: Session,
    *,
    email: str,
    purpose: Purpose,
    fingerprint: str,
) -> None:
    now = utc_now()
    latest = db.scalar(
        select(AuthChallenge.created_at)
        .where(
            AuthChallenge.email_normalized == email,
            AuthChallenge.purpose == purpose,
        )
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
    )
    if latest is not None and _as_utc(latest) > now - CHALLENGE_COOLDOWN:
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "auth.code_cooldown")

    recent = db.scalar(
        select(func.count(AuthChallenge.id)).where(
            AuthChallenge.created_at >= now - CHALLENGE_WINDOW,
            (AuthChallenge.email_normalized == email)
            | (AuthChallenge.request_fingerprint == fingerprint),
        )
    )
    if (recent or 0) >= CHALLENGE_WINDOW_LIMIT:
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "auth.rate_limited")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _create_challenge(
    db: Session,
    *,
    settings: AuthSettings,
    email: str,
    purpose: Purpose,
    fingerprint: str,
) -> tuple[AuthChallenge, str]:
    code = generate_verification_code()
    challenge = AuthChallenge(
        email_normalized=email,
        purpose=purpose,
        code_digest=challenge_digest(
            settings.secret,
            purpose=purpose,
            email_normalized=email,
            code=code,
        ),
        expires_at=utc_now() + CHALLENGE_TTL,
        request_fingerprint=fingerprint,
    )
    db.add(challenge)
    return challenge, code


def _consume_challenge(
    db: Session,
    *,
    settings: AuthSettings,
    email: str,
    purpose: Purpose,
    code: str,
) -> AuthChallenge:
    challenge = db.scalar(
        select(AuthChallenge)
        .where(
            AuthChallenge.email_normalized == email,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
        )
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
    )
    now = utc_now()
    if challenge is None or _as_utc(challenge.expires_at) <= now:
        raise _error(status.HTTP_400_BAD_REQUEST, "auth.invalid_code")

    supplied = challenge_digest(
        settings.secret,
        purpose=purpose,
        email_normalized=email,
        code=code,
    )
    if not hmac.compare_digest(challenge.code_digest, supplied):
        challenge.attempts += 1
        if challenge.attempts >= CHALLENGE_MAX_ATTEMPTS:
            challenge.consumed_at = now
        db.commit()
        raise _error(status.HTTP_400_BAD_REQUEST, "auth.invalid_code")
    challenge.consumed_at = now
    return challenge


def _new_auth_session(
    db: Session,
    *,
    settings: AuthSettings,
    user: User,
) -> str:
    token = new_session_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_digest=session_digest(settings.secret, token),
            expires_at=utc_now() + SESSION_TTL,
        )
    )
    return token


def _session_projection(user: User, email: str) -> dict[str, object]:
    return {
        "authenticated": True,
        "subject": user.oidc_subject,
        "displayName": user.display_name,
        "email": email,
    }


@router.get("/config")
def read_auth_config(settings: SettingsDependency) -> dict[str, object]:
    return {
        "enabled": settings.enabled,
        "passwordEnabled": settings.password_enabled,
        "providers": {
            "github": settings.enabled and settings.github_enabled,
            "google": settings.enabled and settings.google_enabled,
        },
    }


@router.get("/github/start")
def start_github_oauth(
    settings: SettingsDependency,
    returnTo: str | None = None,
) -> RedirectResponse:
    _require_github_enabled(settings)
    state = new_session_token()
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
    )
    response = RedirectResponse(f"https://github.com/login/oauth/authorize?{query}")
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        max_age=600,
        path="/",
        samesite="lax",
        secure=settings.cookie_secure,
    )
    response.set_cookie(
        OAUTH_RETURN_COOKIE,
        _safe_return_to(returnTo),
        httponly=True,
        max_age=600,
        path="/",
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return response


@router.get("/github/callback")
def complete_github_oauth(
    request: Request,
    db: SessionDependency,
    settings: SettingsDependency,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    _require_github_enabled(settings)
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    return_to = _safe_return_to(request.cookies.get(OAUTH_RETURN_COOKIE))
    if (
        not code
        or not state
        or not expected_state
        or not hmac.compare_digest(state, expected_state)
    ):
        return RedirectResponse(_auth_result_url(return_to, "invalid"))
    try:
        profile = exchange_github_code(settings, code)
    except GitHubOAuthError:
        return RedirectResponse(_auth_result_url(return_to, "failed"))

    identity = db.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == "github",
            OAuthIdentity.provider_subject == profile.subject,
        )
    )
    if identity is None:
        user = User(
            oidc_subject=f"github:{profile.subject}",
            display_name=profile.display_name[:120],
        )
        db.add(user)
        db.flush()
        identity = OAuthIdentity(
            user_id=user.id,
            provider="github",
            provider_subject=profile.subject,
            email=profile.email,
            display_name=profile.display_name[:120],
            avatar_url=profile.avatar_url,
        )
        db.add(identity)
    else:
        existing_user = db.get(User, identity.user_id)
        if existing_user is None:
            raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "auth.identity_invalid")
        user = existing_user
        identity.email = profile.email
        identity.display_name = profile.display_name[:120]
        identity.avatar_url = profile.avatar_url
        user.display_name = profile.display_name[:120]

    token = _new_auth_session(db, settings=settings, user=user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "auth.identity_conflict") from error
    response = RedirectResponse(return_to)
    set_session_cookie(response, token, secure=settings.cookie_secure)
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(OAUTH_RETURN_COOKIE, path="/")
    return response


@router.get("/session")
def read_auth_session(request: Request, db: SessionDependency) -> dict[str, object]:
    try:
        principal = current_principal(request, db)
    except HTTPException as error:
        if error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        return {"authenticated": False}
    return {
        "authenticated": True,
        "subject": principal.subject,
        "displayName": principal.claims.get("name"),
        "email": principal.claims.get("email"),
    }


@router.post("/register/request", status_code=status.HTTP_202_ACCEPTED)
def request_registration_code(
    payload: ChallengeRequest,
    request: Request,
    db: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    _require_password_enabled(settings)
    _validate_origin(request, settings)
    email = _validated_email(payload.email)
    if db.scalar(select(AuthCredential.user_id).where(AuthCredential.email_normalized == email)):
        raise _error(status.HTTP_409_CONFLICT, "auth.email_exists")
    fingerprint = _client_fingerprint(request, settings)
    _check_challenge_rate_limit(db, email=email, purpose="register", fingerprint=fingerprint)
    _, code = _create_challenge(
        db,
        settings=settings,
        email=email,
        purpose="register",
        fingerprint=fingerprint,
    )
    try:
        send_verification_email(
            settings,
            email=email,
            code=code,
            purpose="register",
            locale=payload.locale,
        )
    except EmailDeliveryError as error:
        db.rollback()
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.email_unavailable") from error
    db.commit()
    result: dict[str, object] = {"accepted": True, "expiresIn": 600}
    if settings.debug_codes:
        result["debugCode"] = code
    return result


@router.post("/register/complete", status_code=status.HTTP_201_CREATED)
def complete_registration(
    payload: RegistrationRequest,
    request: Request,
    response: Response,
    db: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    _require_password_enabled(settings)
    _validate_origin(request, settings)
    email = _validated_email(payload.email)
    password = _validated_password(payload.password)
    display_name = _normalized_display_name(payload.display_name)
    if db.scalar(select(AuthCredential.user_id).where(AuthCredential.email_normalized == email)):
        raise _error(status.HTTP_409_CONFLICT, "auth.email_exists")
    _consume_challenge(
        db,
        settings=settings,
        email=email,
        purpose="register",
        code=payload.code,
    )
    user = User(oidc_subject=email_subject(email), display_name=display_name)
    db.add(user)
    db.flush()
    db.add(
        AuthCredential(
            user_id=user.id,
            email_normalized=email,
            password_hash=hash_password(password),
        )
    )
    token = _new_auth_session(db, settings=settings, user=user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "auth.email_exists") from error
    set_session_cookie(response, token, secure=settings.cookie_secure)
    return _session_projection(user, email)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    _require_password_enabled(settings)
    _validate_origin(request, settings)
    email = _validated_email(payload.email)
    row = db.execute(
        select(AuthCredential, User)
        .join(User, User.id == AuthCredential.user_id)
        .where(AuthCredential.email_normalized == email)
    ).first()
    credential, user = row if row is not None else (None, None)
    now = utc_now()
    if (
        credential is not None
        and credential.locked_until is not None
        and _as_utc(credential.locked_until) > now
    ):
        raise _error(status.HTTP_429_TOO_MANY_REQUESTS, "auth.account_locked")

    encoded = credential.password_hash if credential is not None else DUMMY_PASSWORD_HASH
    valid = verify_password(payload.password, encoded)
    if credential is None or user is None or not valid:
        if credential is not None:
            credential.failed_attempts += 1
            if credential.failed_attempts >= LOGIN_FAILURE_LIMIT:
                credential.locked_until = now + LOGIN_LOCK_TIME
            credential.updated_at = now
            db.commit()
        raise _error(status.HTTP_401_UNAUTHORIZED, "auth.invalid_credentials")

    credential.failed_attempts = 0
    credential.locked_until = None
    credential.updated_at = now
    token = _new_auth_session(db, settings=settings, user=user)
    db.commit()
    set_session_cookie(response, token, secure=settings.cookie_secure)
    return _session_projection(user, email)


@router.post("/password/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: ChallengeRequest,
    request: Request,
    db: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    _require_password_enabled(settings)
    _validate_origin(request, settings)
    email = _validated_email(payload.email)
    fingerprint = _client_fingerprint(request, settings)
    _check_challenge_rate_limit(db, email=email, purpose="password_reset", fingerprint=fingerprint)
    _, code = _create_challenge(
        db,
        settings=settings,
        email=email,
        purpose="password_reset",
        fingerprint=fingerprint,
    )
    exists = db.scalar(
        select(AuthCredential.user_id).where(AuthCredential.email_normalized == email)
    )
    if exists is not None:
        try:
            send_verification_email(
                settings,
                email=email,
                code=code,
                purpose="password_reset",
                locale=payload.locale,
            )
        except EmailDeliveryError as error:
            db.rollback()
            raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.email_unavailable") from error
    db.commit()
    result: dict[str, object] = {"accepted": True, "expiresIn": 600}
    if settings.debug_codes and exists is not None:
        result["debugCode"] = code
    return result


@router.post("/password/reset")
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
    db: SessionDependency,
    settings: SettingsDependency,
) -> dict[str, object]:
    _require_password_enabled(settings)
    _validate_origin(request, settings)
    email = _validated_email(payload.email)
    password = _validated_password(payload.password)
    row = db.execute(
        select(AuthCredential, User)
        .join(User, User.id == AuthCredential.user_id)
        .where(AuthCredential.email_normalized == email)
    ).first()
    if row is None:
        raise _error(status.HTTP_400_BAD_REQUEST, "auth.invalid_code")
    credential, user = row
    _consume_challenge(
        db,
        settings=settings,
        email=email,
        purpose="password_reset",
        code=payload.code,
    )
    now = utc_now()
    credential.password_hash = hash_password(password)
    credential.failed_attempts = 0
    credential.locked_until = None
    credential.updated_at = now
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    token = _new_auth_session(db, settings=settings, user=user)
    db.commit()
    set_session_cookie(response, token, secure=settings.cookie_secure)
    return _session_projection(user, email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: SessionDependency,
    settings: SettingsDependency,
) -> None:
    _validate_origin(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    if token and settings.secret:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_digest == session_digest(settings.secret, token))
            .values(revoked_at=utc_now())
        )
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
