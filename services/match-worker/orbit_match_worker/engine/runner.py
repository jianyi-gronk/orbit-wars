"""Deterministic scripted match runner with authoritative command/frame logs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from orbit_engine import (
    ActionFormatError,
    EngineSnapshot,
    LaunchCommand,
    decode_raw_action,
    encode_action,
)
from orbit_engine.hashing import normalize_for_hash

from orbit_match_worker.engine.adapter import EngineAdapter
from orbit_match_worker.engine.state_machine import (
    MatchStateMachine,
    MatchStatus,
    PlatformFailure,
    PlayerForfeit,
    TransitionRecord,
)

PlayerViews = tuple[EngineSnapshot, EngineSnapshot]
ActionProvider = Callable[[int, PlayerViews], tuple[object, object]]


class PlayerControllerError(RuntimeError):
    def __init__(self, slot: int, code: str) -> None:
        super().__init__(code)
        if slot not in (0, 1):
            raise ValueError("controller error slot must be 0 or 1")
        self.slot = slot
        self.code = code


class PlatformExecutionError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class MatchSpec:
    match_id: str
    ruleset_id: str
    seed: int
    slots: tuple[int, int] = (0, 1)

    def __post_init__(self) -> None:
        if not self.match_id:
            raise ValueError("match_id cannot be empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if self.slots != (0, 1):
            raise ValueError("2P match slots must be exactly (0, 1)")


@dataclass(frozen=True, slots=True)
class CommandRecord:
    step: int
    slot: int
    payload: tuple[tuple[int | float, int | float, int | float], ...]
    command_hash: str


@dataclass(frozen=True, slots=True)
class AuthoritativeFrame:
    step: int
    state_hash: str
    snapshot: EngineSnapshot


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    winner_slot: int | None
    reason: str
    final_step: int
    rewards: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class MatchRunResult:
    spec: MatchSpec
    status: MatchStatus
    transitions: tuple[TransitionRecord, ...]
    commands: tuple[CommandRecord, ...]
    frames: tuple[AuthoritativeFrame, ...]
    outcome: MatchOutcome | None
    failure: PlatformFailure | PlayerForfeit | None


class MatchRunner:
    def __init__(self, spec: MatchSpec) -> None:
        self.spec = spec
        self._state = MatchStateMachine()
        self._adapter = EngineAdapter(spec.ruleset_id)
        self._commands: list[CommandRecord] = []
        self._frames: list[AuthoritativeFrame] = []

    def run(self, action_provider: ActionProvider) -> MatchRunResult:
        self._state.transition(MatchStatus.PREPARING)
        try:
            initial = self._adapter.reset(seed=self.spec.seed, slots=self.spec.slots)
            self._record_frame(initial)
            self._state.transition(MatchStatus.READY)
            self._state.transition(MatchStatus.RUNNING)

            while not self._adapter.done:
                step = self._adapter.snapshot().step
                views = (
                    self._adapter.snapshot(player=0),
                    self._adapter.snapshot(player=1),
                )
                raw_actions = action_provider(step, views)
                commands = self._decode_actions(raw_actions)
                self._record_commands(step, commands)
                result = self._adapter.step(commands)
                self._record_frame(result.snapshot)

            self._state.transition(MatchStatus.FINALIZING)
            outcome = self._engine_outcome(self._frames[-1].snapshot)
            self._state.transition(MatchStatus.FINISHED)
            return self._result(outcome=outcome, failure=None)
        except PlayerControllerError as exc:
            return self._forfeit(exc)
        except PlatformExecutionError as exc:
            return self._fail(PlatformFailure(code=exc.code, detail=exc.detail))
        except Exception as exc:
            return self._fail(
                PlatformFailure(code="platform.execution_error", detail=type(exc).__name__)
            )

    def _decode_actions(
        self,
        raw_actions: tuple[object, object],
    ) -> list[list[LaunchCommand]]:
        if not isinstance(raw_actions, tuple) or len(raw_actions) != 2:
            raise PlatformExecutionError("platform.invalid_action_provider_result")
        decoded: list[list[LaunchCommand]] = []
        for slot, raw_action in enumerate(raw_actions):
            try:
                decoded.append(decode_raw_action(raw_action))
            except ActionFormatError as exc:
                raise PlayerControllerError(slot, "controller.invalid_action") from exc
        return decoded

    def _record_commands(self, step: int, actions: list[list[LaunchCommand]]) -> None:
        for slot, commands in enumerate(actions):
            raw = encode_action(commands)
            payload = tuple((command[0], command[1], command[2]) for command in raw)
            encoded = json.dumps(
                normalize_for_hash(raw),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            self._commands.append(
                CommandRecord(
                    step=step,
                    slot=slot,
                    payload=payload,
                    command_hash=hashlib.sha256(encoded).hexdigest(),
                )
            )

    def _record_frame(self, snapshot: EngineSnapshot) -> None:
        self._frames.append(
            AuthoritativeFrame(
                step=snapshot.step,
                state_hash=snapshot.state_hash,
                snapshot=snapshot,
            )
        )

    def _forfeit(self, error: PlayerControllerError) -> MatchRunResult:
        cause = PlayerForfeit(slot=error.slot, code=error.code)
        if self._state.status is not MatchStatus.RUNNING:
            return self._fail(
                PlatformFailure(
                    code="platform.invalid_forfeit_state",
                    detail=self._state.status,
                )
            )
        self._state.transition(MatchStatus.FORFEITED, cause=cause)
        self._state.transition(MatchStatus.FINALIZING)
        final_step = self._frames[-1].step
        winner = 1 - error.slot
        outcome = MatchOutcome(
            winner_slot=winner,
            reason="forfeit",
            final_step=final_step,
            rewards=tuple(1 if slot == winner else -1 for slot in self.spec.slots),
        )
        self._state.transition(MatchStatus.FINISHED)
        return self._result(outcome=outcome, failure=cause)

    def _fail(self, failure: PlatformFailure) -> MatchRunResult:
        if self._state.status in (
            MatchStatus.PREPARING,
            MatchStatus.READY,
            MatchStatus.RUNNING,
            MatchStatus.FINALIZING,
        ):
            self._state.transition(MatchStatus.FAILED, cause=failure)
        return self._result(outcome=None, failure=failure)

    def _engine_outcome(self, snapshot: EngineSnapshot) -> MatchOutcome:
        winners = [slot for slot, reward in enumerate(snapshot.rewards) if reward == 1]
        winner = winners[0] if len(winners) == 1 else None
        reason = (
            "step_limit" if snapshot.step >= snapshot.config.episode_steps - 1 else "elimination"
        )
        return MatchOutcome(
            winner_slot=winner,
            reason=reason,
            final_step=snapshot.step,
            rewards=snapshot.rewards,
        )

    def _result(
        self,
        *,
        outcome: MatchOutcome | None,
        failure: PlatformFailure | PlayerForfeit | None,
    ) -> MatchRunResult:
        return MatchRunResult(
            spec=self.spec,
            status=self._state.status,
            transitions=self._state.history,
            commands=tuple(self._commands),
            frames=tuple(self._frames),
            outcome=outcome,
            failure=failure,
        )
