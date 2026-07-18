"""Server-authoritative turn windows with monotonic deadline checks."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class TurnWindow:
    step: int
    opened_at: datetime
    deadline_at: datetime
    monotonic_deadline: float


class TurnClock:
    def __init__(
        self,
        duration_seconds: float = 3.0,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], datetime] | None = None,
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("turn duration must be positive")
        self.duration_seconds = duration_seconds
        self._monotonic = monotonic
        self._wall_time = wall_time or (lambda: datetime.now(UTC))

    def open(self, step: int) -> TurnWindow:
        if step < 0:
            raise ValueError("step must be non-negative")
        opened_at = self._wall_time()
        return TurnWindow(
            step=step,
            opened_at=opened_at,
            deadline_at=opened_at + timedelta(seconds=self.duration_seconds),
            monotonic_deadline=self._monotonic() + self.duration_seconds,
        )

    def is_open(self, window: TurnWindow, *, received_at: float | None = None) -> bool:
        instant = self._monotonic() if received_at is None else received_at
        return instant <= window.monotonic_deadline

    def has_elapsed(self, window: TurnWindow) -> bool:
        return not self.is_open(window)
