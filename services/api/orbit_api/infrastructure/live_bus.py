"""Redis Streams boundary for commands and authoritative live-match events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from os import environ
from typing import Any, Protocol, cast

from redis.asyncio import Redis


class LiveMatchBus(Protocol):
    async def snapshot(self, match_id: str, slot: int) -> dict[str, Any] | None: ...

    async def publish_command(self, match_id: str, slot: int, command: dict[str, Any]) -> None: ...

    async def history(self, match_id: str, after_step: int) -> list[dict[str, Any]]: ...

    def subscribe(self, match_id: str) -> AsyncIterator[dict[str, Any]]: ...


def _event_step(event: dict[str, Any]) -> int:
    step = event.get("step")
    if isinstance(step, int):
        return int(step)
    payload = event.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("step"), int):
        return int(payload["step"])
    result = event.get("result")
    if isinstance(result, dict) and isinstance(result.get("finalStep"), int):
        return int(result["finalStep"])
    return -1


def _ordered_unique(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        unique.setdefault(json.dumps(event, sort_keys=True, separators=(",", ":")), event)
    order = {"turn.open": 0, "turn.accepted": 1, "turn.closed": 2, "match.frame": 3}
    return sorted(
        unique.values(),
        key=lambda event: (_event_step(event), order.get(str(event.get("type")), 9)),
    )


class MemoryLiveMatchBus:
    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, int], dict[str, Any]] = {}
        self.commands: list[tuple[str, int, dict[str, Any]]] = []
        self.events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def snapshot(self, match_id: str, slot: int) -> dict[str, Any] | None:
        return self.snapshots.get((match_id, slot))

    async def publish_command(self, match_id: str, slot: int, command: dict[str, Any]) -> None:
        self.commands.append((match_id, slot, command))

    async def history(self, match_id: str, after_step: int) -> list[dict[str, Any]]:
        return _ordered_unique(
            [event for event in self.events[match_id] if _event_step(event) > after_step]
        )

    async def publish_event(self, match_id: str, event: dict[str, Any]) -> None:
        self.events[match_id].append(event)
        for queue in tuple(self.subscribers[match_id]):
            await queue.put(event)

    async def _subscription(self, match_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers[match_id].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.subscribers[match_id].remove(queue)

    def subscribe(self, match_id: str) -> AsyncIterator[dict[str, Any]]:
        return self._subscription(match_id)


class RedisLiveMatchBus:
    def __init__(self, client: Redis) -> None:
        self.client = client

    @classmethod
    def from_environment(cls) -> RedisLiveMatchBus:
        return cls(
            Redis.from_url(
                environ.get("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
        )

    @staticmethod
    def _events_key(match_id: str) -> str:
        return f"orbit:match:{match_id}:events:v1"

    async def snapshot(self, match_id: str, slot: int) -> dict[str, Any] | None:
        encoded = await self.client.get(f"orbit:match:{match_id}:snapshot:{slot}:v1")
        if encoded is None:
            return None
        decoded = json.loads(encoded)
        return cast(dict[str, Any], decoded)

    async def set_snapshot(self, match_id: str, slot: int, snapshot: dict[str, Any]) -> None:
        await self.client.set(
            f"orbit:match:{match_id}:snapshot:{slot}:v1",
            json.dumps(snapshot, separators=(",", ":")),
            ex=3600,
        )

    async def publish_command(self, match_id: str, slot: int, command: dict[str, Any]) -> None:
        await self.client.xadd(
            f"orbit:match:{match_id}:commands:v1",
            {"slot": str(slot), "payload": json.dumps(command, separators=(",", ":"))},
            maxlen=2048,
        )

    async def publish_event(self, match_id: str, event: dict[str, Any]) -> None:
        await self.client.xadd(
            self._events_key(match_id),
            {"payload": json.dumps(event, separators=(",", ":"))},
            maxlen=4096,
        )

    async def history(self, match_id: str, after_step: int) -> list[dict[str, Any]]:
        raw_rows = await self.client.xrange(self._events_key(match_id))
        rows = cast(list[tuple[str, dict[str, str]]], raw_rows)
        events = [cast(dict[str, Any], json.loads(fields["payload"])) for _row_id, fields in rows]
        return _ordered_unique([event for event in events if _event_step(event) > after_step])

    async def _subscription(self, match_id: str) -> AsyncIterator[dict[str, Any]]:
        stream = self._events_key(match_id)
        cursor: str | bytes = "$"
        while True:
            raw_rows = await self.client.xread({stream: cursor}, block=1000, count=100)
            rows = cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], raw_rows)
            for _stream_name, entries in rows:
                for row_id, fields in entries:
                    cursor = row_id
                    yield cast(dict[str, Any], json.loads(fields["payload"]))

    def subscribe(self, match_id: str) -> AsyncIterator[dict[str, Any]]:
        return self._subscription(match_id)
