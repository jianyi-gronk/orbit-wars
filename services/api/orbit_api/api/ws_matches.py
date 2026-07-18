"""Ticket-authenticated WebSocket gateway for live matches."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from orbit_contracts.models import MatchResyncMessageV1, TurnSubmitMessageV1
from pydantic import ValidationError

from orbit_api.domain.match_tickets import MatchTicketError, MatchTicketService
from orbit_api.infrastructure.live_bus import LiveMatchBus, RedisLiveMatchBus

router = APIRouter()


def _bus(websocket: WebSocket) -> LiveMatchBus:
    bus = getattr(websocket.app.state, "live_match_bus", None)
    if bus is None:
        bus = RedisLiveMatchBus.from_environment()
        websocket.app.state.live_match_bus = bus
    return bus


def _tickets(websocket: WebSocket) -> MatchTicketService:
    service = getattr(websocket.app.state, "match_ticket_service", None)
    if service is None:
        service = MatchTicketService()
        websocket.app.state.match_ticket_service = service
    return service


async def _send_events(websocket: WebSocket, bus: LiveMatchBus, match_id: str) -> None:
    async for event in bus.subscribe(match_id):
        await websocket.send_json(event)


@router.websocket("/api/live/v1/matches/{match_id}")
async def live_match(websocket: WebSocket, match_id: str, ticket: str) -> None:
    try:
        claims = _tickets(websocket).verify(ticket, expected_match_id=match_id)
    except MatchTicketError:
        await websocket.close(code=4401, reason="match_ticket.invalid")
        return
    await websocket.accept()
    bus = _bus(websocket)
    snapshot = await bus.snapshot(match_id, claims.slot)
    if snapshot is not None:
        await websocket.send_json(snapshot)
    sender = asyncio.create_task(_send_events(websocket, bus, match_id))
    try:
        while True:
            raw: dict[str, Any] = await websocket.receive_json()
            message_type = raw.get("type")
            if message_type == "match.resync":
                try:
                    message = MatchResyncMessageV1.model_validate(raw)
                except ValidationError:
                    await websocket.send_json(
                        {"type": "match.error", "code": "message.invalid", "recoverable": True}
                    )
                    continue
                for event in await bus.history(match_id, message.last_seen_step):
                    await websocket.send_json(event)
                continue
            if message_type != "turn.submit":
                await websocket.send_json(
                    {"type": "match.error", "code": "message.unsupported", "recoverable": True}
                )
                continue
            try:
                submission = TurnSubmitMessageV1.model_validate(raw)
                if submission.payload.match_id != match_id:
                    raise ValueError
            except (ValidationError, ValueError):
                await websocket.send_json(
                    {"type": "match.error", "code": "command.invalid", "recoverable": True}
                )
                continue
            payload = submission.payload.model_dump(mode="json", by_alias=True)
            command_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            await bus.publish_command(match_id, claims.slot, payload)
            await websocket.send_json(
                {
                    "type": "turn.accepted",
                    "step": submission.payload.expected_step,
                    "commandHash": command_hash,
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender
