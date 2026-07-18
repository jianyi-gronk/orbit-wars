"""Authoritative engine adapter and match execution primitives."""

from orbit_match_worker.engine.adapter import EngineAdapter
from orbit_match_worker.engine.runner import (
    MatchOutcome,
    MatchRunner,
    MatchRunResult,
    MatchSpec,
    PlatformExecutionError,
    PlayerControllerError,
)
from orbit_match_worker.engine.state_machine import (
    MatchStateMachine,
    MatchStatus,
    PlatformFailure,
    PlayerForfeit,
    TransitionError,
)

__all__ = [
    "EngineAdapter",
    "MatchOutcome",
    "MatchRunResult",
    "MatchRunner",
    "MatchSpec",
    "MatchStateMachine",
    "MatchStatus",
    "PlatformExecutionError",
    "PlatformFailure",
    "PlayerControllerError",
    "PlayerForfeit",
    "TransitionError",
]
