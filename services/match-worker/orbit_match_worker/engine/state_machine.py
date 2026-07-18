"""Strict lifecycle for authoritative match execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MatchStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    FINALIZING = "finalizing"
    FINISHED = "finished"
    FAILED = "failed"
    FORFEITED = "forfeited"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PlatformFailure:
    code: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PlayerForfeit:
    slot: int
    code: str

    def __post_init__(self) -> None:
        if self.slot not in (0, 1):
            raise ValueError("forfeit slot must be 0 or 1")


TransitionCause = PlatformFailure | PlayerForfeit


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    sequence: int
    previous: MatchStatus
    current: MatchStatus
    cause: TransitionCause | None = None


class TransitionError(RuntimeError):
    pass


_ALLOWED_TRANSITIONS: dict[MatchStatus, frozenset[MatchStatus]] = {
    MatchStatus.QUEUED: frozenset({MatchStatus.PREPARING, MatchStatus.CANCELLED}),
    MatchStatus.PREPARING: frozenset(
        {MatchStatus.READY, MatchStatus.FAILED, MatchStatus.CANCELLED}
    ),
    MatchStatus.READY: frozenset({MatchStatus.RUNNING, MatchStatus.FAILED}),
    MatchStatus.RUNNING: frozenset(
        {MatchStatus.FINALIZING, MatchStatus.FORFEITED, MatchStatus.FAILED}
    ),
    MatchStatus.FORFEITED: frozenset({MatchStatus.FINALIZING}),
    MatchStatus.FINALIZING: frozenset({MatchStatus.FINISHED, MatchStatus.FAILED}),
    MatchStatus.FINISHED: frozenset(),
    MatchStatus.FAILED: frozenset(),
    MatchStatus.CANCELLED: frozenset(),
}


class MatchStateMachine:
    def __init__(self) -> None:
        self._status = MatchStatus.QUEUED
        self._history: list[TransitionRecord] = []

    @property
    def status(self) -> MatchStatus:
        return self._status

    @property
    def history(self) -> tuple[TransitionRecord, ...]:
        return tuple(self._history)

    def transition(
        self,
        target: MatchStatus,
        *,
        cause: TransitionCause | None = None,
    ) -> TransitionRecord:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise TransitionError(f"cannot transition from {self._status} to {target}")
        if target is MatchStatus.FAILED and not isinstance(cause, PlatformFailure):
            raise TransitionError("failed status requires a platform failure cause")
        if target is MatchStatus.FORFEITED and not isinstance(cause, PlayerForfeit):
            raise TransitionError("forfeited status requires a player forfeit cause")
        if target not in (MatchStatus.FAILED, MatchStatus.FORFEITED) and cause is not None:
            raise TransitionError(f"{target} does not accept a failure cause")

        record = TransitionRecord(
            sequence=len(self._history),
            previous=self._status,
            current=target,
            cause=cause,
        )
        self._status = target
        self._history.append(record)
        return record
