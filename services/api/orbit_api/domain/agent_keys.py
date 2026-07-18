"""One-time Agent Key issuance, scoped authentication, and revocation."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from os import environ

from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import AgentKey, Fleet
from orbit_api.domain.fleets import FleetNotFoundError, get_owned_fleet
from orbit_api.security.oidc import Principal

ALLOWED_SCOPES = frozenset(
    {
        "fleet:read",
        "version:read",
        "version:write",
        "matches:read",
        "opponents:read",
        "simulate",
        "challenge",
    }
)


class AgentKeyError(Exception):
    code = "agent_key.error"


class AgentKeyInvalidError(AgentKeyError):
    code = "agent_key.invalid"


class AgentKeyScopeError(AgentKeyError):
    code = "agent_key.insufficient_scope"


@dataclass(frozen=True)
class IssuedAgentKey:
    credential: str
    public_prefix: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class AgentKeyContext:
    key: AgentKey
    fleet: Fleet


def issue_agent_key(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
    scopes: list[str],
) -> IssuedAgentKey:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    normalized = tuple(sorted(set(scopes)))
    if not normalized or not set(normalized) <= ALLOWED_SCOPES:
        raise AgentKeyScopeError("one or more scopes are invalid")
    prefix = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
    secret = secrets.token_urlsafe(32)
    key = AgentKey(
        fleet_id=fleet.id,
        public_prefix=prefix,
        secret_digest=_digest(secret),
        scopes=list(normalized),
    )
    session.add(key)
    session.commit()
    return IssuedAgentKey(
        credential=f"owk_{prefix}_{secret}",
        public_prefix=prefix,
        scopes=normalized,
    )


def authenticate_agent_key(
    session: Session,
    credential: str,
    *,
    required_scope: str,
) -> AgentKeyContext:
    prefix, secret = _parse(credential)
    key = session.scalar(
        select(AgentKey).where(
            AgentKey.public_prefix == prefix,
            AgentKey.revoked_at.is_(None),
        )
    )
    if key is None or not hmac.compare_digest(key.secret_digest, _digest(secret)):
        raise AgentKeyInvalidError("Agent Key is invalid or revoked")
    if required_scope not in key.scopes:
        raise AgentKeyScopeError("Agent Key does not have the required scope")
    fleet = session.scalar(select(Fleet).where(Fleet.id == key.fleet_id))
    if fleet is None:
        raise AgentKeyInvalidError("Agent Key fleet no longer exists")
    key.last_used_at = utc_now()
    session.commit()
    return AgentKeyContext(key=key, fleet=fleet)


def revoke_agent_key(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
    public_prefix: str,
) -> datetime:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    key = session.scalar(
        select(AgentKey).where(
            AgentKey.fleet_id == fleet.id,
            AgentKey.public_prefix == public_prefix,
        )
    )
    if key is None:
        raise FleetNotFoundError("Agent Key was not found")
    if key.revoked_at is None:
        key.revoked_at = utc_now()
        session.commit()
    return key.revoked_at


def _parse(credential: str) -> tuple[str, str]:
    parts = credential.split("_", 2)
    if len(parts) != 3 or parts[0] != "owk" or not parts[1] or not parts[2]:
        raise AgentKeyInvalidError("Agent Key is malformed")
    return parts[1], parts[2]


def _digest(secret: str) -> str:
    pepper = environ.get("AGENT_KEY_PEPPER", "local-agent-key-pepper-change-in-production")
    return hmac.new(pepper.encode(), secret.encode(), hashlib.sha256).hexdigest()
