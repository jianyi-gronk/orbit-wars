"""Checkpointed deterministic recovery and idempotent finalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, cast

from orbit_engine import EngineSnapshot, OrbitEngine

from orbit_match_worker.engine.runner import PlayerControllerError
from orbit_match_worker.runtime.telemetry import worker_metrics


class RecoveryConflict(RuntimeError):
    pass


class DeterminismRecoveryError(RuntimeError):
    code = "platform.recovery_hash_mismatch"


@dataclass(frozen=True, slots=True)
class PersistedCommandStep:
    step: int
    actions: tuple[tuple[tuple[int | float, ...], ...], ...]
    command_hash: str

    @classmethod
    def create(cls, step: int, actions: object) -> PersistedCommandStep:
        if not isinstance(actions, (list, tuple)) or len(actions) != 2:
            raise ValueError("two action batches are required")
        batches = cast(list[list[list[int | float]]], actions)
        normalized = tuple(tuple(tuple(command) for command in batch) for batch in batches)
        encoded = json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode()
        return cls(step, normalized, hashlib.sha256(encoded).hexdigest())

    def raw(self) -> list[list[list[int | float]]]:
        return [[list(command) for command in batch] for batch in self.actions]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    step: int
    state_hash: str


class RecoveryStore(Protocol):
    def append(self, match_id: str, command: PersistedCommandStep) -> None: ...

    def checkpoint(self, match_id: str, checkpoint: Checkpoint) -> None: ...

    def commands(self, match_id: str) -> tuple[PersistedCommandStep, ...]: ...

    def latest_checkpoint(self, match_id: str) -> Checkpoint | None: ...


class MemoryRecoveryStore:
    def __init__(self) -> None:
        self.command_logs: dict[str, dict[int, PersistedCommandStep]] = {}
        self.checkpoints: dict[str, dict[int, Checkpoint]] = {}

    def append(self, match_id: str, command: PersistedCommandStep) -> None:
        log = self.command_logs.setdefault(match_id, {})
        existing = log.get(command.step)
        if existing is not None and existing.command_hash != command.command_hash:
            raise RecoveryConflict("a different command already exists at this step")
        log[command.step] = command

    def checkpoint(self, match_id: str, checkpoint: Checkpoint) -> None:
        checkpoints = self.checkpoints.setdefault(match_id, {})
        existing = checkpoints.get(checkpoint.step)
        if existing is not None and existing.state_hash != checkpoint.state_hash:
            raise RecoveryConflict("a different checkpoint already exists at this step")
        checkpoints[checkpoint.step] = checkpoint

    def commands(self, match_id: str) -> tuple[PersistedCommandStep, ...]:
        return tuple(
            command for _step, command in sorted(self.command_logs.get(match_id, {}).items())
        )

    def latest_checkpoint(self, match_id: str) -> Checkpoint | None:
        checkpoints = self.checkpoints.get(match_id, {})
        return checkpoints[max(checkpoints)] if checkpoints else None


class MatchJournal:
    def __init__(
        self,
        match_id: str,
        store: RecoveryStore,
        *,
        checkpoint_interval: int = 20,
    ) -> None:
        self.match_id = match_id
        self.store = store
        self.checkpoint_interval = checkpoint_interval

    def record(self, step: int, actions: object, snapshot: EngineSnapshot) -> None:
        command = PersistedCommandStep.create(step, actions)
        self.store.append(self.match_id, command)
        if snapshot.step % self.checkpoint_interval == 0:
            self.store.checkpoint(
                self.match_id,
                Checkpoint(step=snapshot.step, state_hash=snapshot.state_hash),
            )


def recover_engine(
    match_id: str,
    seed: int,
    store: RecoveryStore,
) -> OrbitEngine:
    engine = OrbitEngine()
    engine.reset(seed=seed)
    checkpoint = store.latest_checkpoint(match_id)
    for expected_step, command in enumerate(store.commands(match_id)):
        if command.step != expected_step:
            raise DeterminismRecoveryError("command log contains a gap")
        snapshot = engine.step_raw(command.raw()).snapshot
        if (
            checkpoint is not None
            and snapshot.step == checkpoint.step
            and snapshot.state_hash != checkpoint.state_hash
        ):
            worker_metrics.add("determinism_mismatch_total")
            raise DeterminismRecoveryError("checkpoint state hash did not reproduce")
    return engine


class DisconnectTracker:
    def __init__(self, *, maximum_missed: int = 10) -> None:
        self.maximum_missed = maximum_missed
        self.missed = [0, 0]

    def record(self, slot: int, submitted: bool, *, human: bool) -> None:
        if not human:
            return
        self.missed[slot] = 0 if submitted else self.missed[slot] + 1
        if self.missed[slot] >= self.maximum_missed:
            raise PlayerControllerError(slot, "human.consecutive_disconnects")


class ReplayUploader(Protocol):
    def upload_once(self, match_id: str) -> str: ...


class RatingSettler(Protocol):
    def settle_once(self, match_id: str) -> None: ...


@dataclass(slots=True)
class FinalizationState:
    replay_id: str | None = None
    rating_settled: bool = False
    finished: bool = False
    attempts: int = 0


class FinalizationCoordinator:
    def __init__(self) -> None:
        self.states: dict[str, FinalizationState] = {}

    def finalize(
        self,
        match_id: str,
        uploader: ReplayUploader,
        rating: RatingSettler,
        *,
        ranked_and_scoreable: bool,
    ) -> FinalizationState:
        state = self.states.setdefault(match_id, FinalizationState())
        if state.finished:
            return state
        state.attempts += 1
        if state.replay_id is None:
            state.replay_id = uploader.upload_once(match_id)
        if ranked_and_scoreable and not state.rating_settled:
            rating.settle_once(match_id)
            state.rating_settled = True
        state.finished = True
        return state
