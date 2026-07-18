"""Shared Observation/CommandBatch boundary for human and Agent controllers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from orbit_contracts.models import CommandBatchV1, ObservationV1

from orbit_match_worker.runtime.turn_clock import TurnClock, TurnWindow


class CommandValidationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TurnReceipt:
    step: int
    slot: int
    command_hash: str
    idempotent_replay: bool = False


class ControllerAdapter(Protocol):
    controller_type: str

    def command(self, observation: ObservationV1) -> CommandBatchV1: ...


def _batch_hash(batch: CommandBatchV1) -> str:
    encoded = json.dumps(
        batch.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_command_batch(
    batch: CommandBatchV1,
    observation: ObservationV1,
    *,
    slot: int,
) -> None:
    if slot not in (0, 1) or observation.player != slot:
        raise CommandValidationError("command.wrong_slot")
    if batch.match_id != observation.match_id:
        raise CommandValidationError("command.wrong_match")
    if batch.expected_step < observation.step:
        raise CommandValidationError("command.replayed_step")
    if batch.expected_step != observation.step:
        raise CommandValidationError("command.wrong_step")

    planets = {planet.id: planet for planet in observation.planets}
    requested: dict[int, int] = {}
    for command in batch.commands:
        planet = planets.get(command.from_planet_id)
        if planet is None:
            raise CommandValidationError("command.source_not_found")
        if planet.owner != slot:
            raise CommandValidationError("command.source_not_owned")
        requested[planet.id] = requested.get(planet.id, 0) + command.ships
        if requested[planet.id] > planet.ships:
            raise CommandValidationError("command.ship_budget_exceeded")


class TurnCoordinator:
    """Keeps both submissions private until the turn closes."""

    def __init__(self, clock: TurnClock | None = None) -> None:
        self.clock = clock or TurnClock()
        self.window: TurnWindow | None = None
        self.observations: tuple[ObservationV1, ObservationV1] | None = None
        self._batches: dict[int, CommandBatchV1] = {}
        self._receipts: dict[int, TurnReceipt] = {}
        self._idempotency: dict[tuple[int, str], str] = {}

    def open(self, observations: tuple[ObservationV1, ObservationV1]) -> TurnWindow:
        first, second = observations
        if first.match_id != second.match_id or first.step != second.step:
            raise CommandValidationError("turn.observation_mismatch")
        if (first.player, second.player) != (0, 1):
            raise CommandValidationError("turn.invalid_player_views")
        self.observations = observations
        self.window = self.clock.open(first.step)
        self._batches.clear()
        self._receipts.clear()
        self._idempotency.clear()
        return self.window

    def submit(
        self,
        slot: int,
        batch: CommandBatchV1,
        *,
        received_at: float | None = None,
    ) -> TurnReceipt:
        if self.window is None or self.observations is None:
            raise CommandValidationError("turn.not_open")
        if slot not in (0, 1):
            raise CommandValidationError("command.wrong_slot")
        if not self.clock.is_open(self.window, received_at=received_at):
            raise CommandValidationError("command.late")
        digest = _batch_hash(batch)
        idempotency = (slot, batch.idempotency_key)
        previous_digest = self._idempotency.get(idempotency)
        if previous_digest is not None:
            if previous_digest != digest:
                raise CommandValidationError("command.idempotency_conflict")
            previous = self._receipts[slot]
            return TurnReceipt(
                step=previous.step,
                slot=previous.slot,
                command_hash=previous.command_hash,
                idempotent_replay=True,
            )
        if slot in self._batches:
            raise CommandValidationError("command.already_submitted")
        validate_command_batch(batch, self.observations[slot], slot=slot)
        receipt = TurnReceipt(self.window.step, slot, digest)
        self._batches[slot] = batch
        self._receipts[slot] = receipt
        self._idempotency[idempotency] = digest
        return receipt

    def close(self, *, force: bool = False) -> tuple[list[list[int | float]], ...]:
        if self.window is None:
            raise CommandValidationError("turn.not_open")
        if not force and len(self._batches) < 2 and not self.clock.has_elapsed(self.window):
            raise CommandValidationError("turn.still_open")
        actions: list[list[list[int | float]]] = []
        for slot in (0, 1):
            batch = self._batches.get(slot)
            actions.append(
                []
                if batch is None
                else [
                    [command.from_planet_id, command.angle, command.ships]
                    for command in batch.commands
                ]
            )
        self.window = None
        self.observations = None
        return tuple(actions)


class HumanAdapter:
    controller_type = "human"

    def __init__(self, batch: CommandBatchV1 | dict[str, Any]) -> None:
        self.batch = (
            batch if isinstance(batch, CommandBatchV1) else CommandBatchV1.model_validate(batch)
        )

    def command(self, observation: ObservationV1) -> CommandBatchV1:
        del observation
        return self.batch


class AgentAdapter:
    controller_type = "agent"

    def __init__(
        self,
        callback: Callable[[dict[str, Any]], CommandBatchV1 | dict[str, Any]],
    ) -> None:
        self.callback = callback

    def command(self, observation: ObservationV1) -> CommandBatchV1:
        response = self.callback(observation.model_dump(mode="json", by_alias=True))
        return (
            response
            if isinstance(response, CommandBatchV1)
            else CommandBatchV1.model_validate(response)
        )
