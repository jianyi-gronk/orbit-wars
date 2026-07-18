"""Durable match queue boundary backed by Redis lists."""

from __future__ import annotations

from os import environ
from typing import Protocol

from redis import Redis


class MatchQueue(Protocol):
    def enqueue(self, match_public_id: str) -> None: ...


class RedisMatchQueue:
    queue_name = "orbit:matches:queued:v1"

    def __init__(self, client: Redis) -> None:
        self.client = client

    @classmethod
    def from_environment(cls) -> RedisMatchQueue:
        return cls(Redis.from_url(environ.get("REDIS_URL", "redis://localhost:6379/0")))

    def enqueue(self, match_public_id: str) -> None:
        self.client.rpush(self.queue_name, match_public_id)


class MemoryMatchQueue:
    def __init__(self) -> None:
        self.items: list[str] = []

    def enqueue(self, match_public_id: str) -> None:
        if match_public_id not in self.items:
            self.items.append(match_public_id)
