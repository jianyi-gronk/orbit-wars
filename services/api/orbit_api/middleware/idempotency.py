"""Database-backed Idempotency-Key handling for mutating JSON APIs."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast

from fastapi import status
from orbit_api.db.base import utc_now
from orbit_api.db.models import IdempotencyRecord
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class IdempotencyDecision:
    state: Literal["reserved", "replay", "conflict", "in_progress"]
    record: IdempotencyRecord


def request_digest(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"\0")
    digest.update(path.encode())
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


def idempotency_scope(request: Request) -> str:
    credential = request.headers.get("Authorization") or request.cookies.get("orbit_session")
    if credential:
        return "auth:" + hashlib.sha256(credential.encode()).hexdigest()[:32]
    client = request.client.host if request.client else "unknown"
    return f"anonymous:{client}"


def reserve(
    session: Session,
    *,
    scope: str,
    key: str,
    method: str,
    path: str,
    digest: str,
) -> IdempotencyDecision:
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            return IdempotencyDecision("conflict", existing)
        if existing.response_status is None:
            return IdempotencyDecision("in_progress", existing)
        return IdempotencyDecision("replay", existing)

    record = IdempotencyRecord(
        scope=scope,
        key=key,
        method=method,
        path=path,
        request_hash=digest,
        expires_at=utc_now() + timedelta(hours=24),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return reserve(
            session,
            scope=scope,
            key=key,
            method=method,
            path=path,
            digest=digest,
        )
    session.refresh(record)
    return IdempotencyDecision("reserved", record)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, session_factory: sessionmaker[Session]) -> None:
        super().__init__(app)
        self.session_factory = session_factory

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        key = request.headers.get("Idempotency-Key")
        if request.method not in MUTATING_METHODS or key is None:
            return await call_next(request)
        if not 8 <= len(key) <= 128:
            return JSONResponse(
                {"detail": "Idempotency-Key must contain 8-128 characters"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        body = await request.body()
        digest = request_digest(request.method, request.url.path, body)
        with self.session_factory() as session:
            decision = reserve(
                session,
                scope=idempotency_scope(request),
                key=key,
                method=request.method,
                path=request.url.path,
                digest=digest,
            )
            if decision.state == "conflict":
                return JSONResponse(
                    {"detail": "Idempotency-Key was already used for another request"},
                    status_code=status.HTTP_409_CONFLICT,
                )
            if decision.state == "in_progress":
                return JSONResponse(
                    {"detail": "request with this Idempotency-Key is still in progress"},
                    status_code=status.HTTP_409_CONFLICT,
                )
            if decision.state == "replay":
                return JSONResponse(
                    decision.record.response_body,
                    status_code=decision.record.response_status or status.HTTP_200_OK,
                    headers={"Idempotency-Replayed": "true"},
                )

            try:
                response = await call_next(request)
                streaming_response = cast(StreamingResponse, response)
                chunks: list[bytes] = []
                async for chunk in streaming_response.body_iterator:
                    chunks.append(chunk.encode() if isinstance(chunk, str) else bytes(chunk))
                response_body = b"".join(chunks)
                parsed_body = json.loads(response_body) if response_body else None
            except Exception:
                session.delete(decision.record)
                session.commit()
                raise

            if response.status_code < 500 and isinstance(parsed_body, (dict, list)):
                decision.record.response_status = response.status_code
                decision.record.response_body = parsed_body
                session.commit()
            else:
                session.delete(decision.record)
                session.commit()

            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )


SessionFactory = Callable[[], Session]
