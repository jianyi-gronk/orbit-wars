"""Short-lived, slot-bound tickets for live match transport."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import environ
from typing import Any

import jwt


@dataclass(frozen=True)
class MatchTicket:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class MatchTicketClaims:
    match_id: str
    fleet_id: str
    slot: int
    subject: str


class MatchTicketError(RuntimeError):
    code = "match_ticket.invalid"


class MatchTicketService:
    issuer = "orbit-wars-api"
    audience = "orbit-wars-live-match"

    def __init__(self, secret: str | None = None, *, lifetime_seconds: int = 300) -> None:
        self.secret = secret or environ.get(
            "MATCH_TICKET_SECRET", "local-match-ticket-secret-change-me"
        )
        self.lifetime_seconds = lifetime_seconds
        if len(self.secret) < 32:
            raise ValueError("match ticket secret must be at least 32 characters")

    def issue(self, *, match_id: str, fleet_id: str, slot: int, subject: str) -> MatchTicket:
        if slot not in (0, 1):
            raise ValueError("slot must be 0 or 1")
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.lifetime_seconds)
        token = jwt.encode(
            {
                "iss": self.issuer,
                "aud": self.audience,
                "sub": subject,
                "iat": now,
                "exp": expires_at,
                "jti": secrets.token_urlsafe(16),
                "match": match_id,
                "fleet": fleet_id,
                "slot": slot,
            },
            self.secret,
            algorithm="HS256",
        )
        return MatchTicket(token=token, expires_at=expires_at)

    def verify(
        self,
        token: str,
        *,
        expected_match_id: str | None = None,
        expected_slot: int | None = None,
    ) -> MatchTicketClaims:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "sub", "match", "fleet", "slot"]},
            )
            match_id = claims["match"]
            fleet_id = claims["fleet"]
            slot = claims["slot"]
            subject = claims["sub"]
            if not all(isinstance(value, str) and value for value in (match_id, fleet_id, subject)):
                raise MatchTicketError
            if slot not in (0, 1):
                raise MatchTicketError
            if expected_match_id is not None and match_id != expected_match_id:
                raise MatchTicketError
            if expected_slot is not None and slot != expected_slot:
                raise MatchTicketError
        except (jwt.PyJWTError, KeyError, MatchTicketError, TypeError) as error:
            raise MatchTicketError("ticket is expired or outside its match slot") from error
        return MatchTicketClaims(match_id, fleet_id, slot, subject)
