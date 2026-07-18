from __future__ import annotations

from datetime import UTC, datetime

import pytest
from orbit_contracts.models import CommandBatchV1, ObservationV1
from orbit_match_worker.runtime import (
    AgentAdapter,
    CommandValidationError,
    HumanAdapter,
    TurnClock,
    TurnCoordinator,
)


def observation(slot: int, *, step: int = 7) -> ObservationV1:
    return ObservationV1.model_validate(
        {
            "schemaVersion": 1,
            "matchId": "match-1",
            "step": step,
            "player": slot,
            "deadlineAt": datetime(2026, 7, 18, 0, 0, 3, tzinfo=UTC),
            "angularVelocity": 0.01,
            "planets": [
                {
                    "id": 0,
                    "owner": 0,
                    "x": 1.0,
                    "y": 1.0,
                    "radius": 2.0,
                    "ships": 10.0,
                    "production": 1.0,
                },
                {
                    "id": 1,
                    "owner": 1,
                    "x": 9.0,
                    "y": 9.0,
                    "radius": 2.0,
                    "ships": 8.0,
                    "production": 1.0,
                },
            ],
            "fleets": [],
            "initialPlanets": [],
            "comets": [],
        }
    )


def batch(slot: int, *, step: int = 7, ships: int = 4, key: str = "request-0001") -> CommandBatchV1:
    return CommandBatchV1.model_validate(
        {
            "schemaVersion": 1,
            "matchId": "match-1",
            "expectedStep": step,
            "commands": [{"fromPlanetId": slot, "angle": 1.2, "ships": ships}],
            "idempotencyKey": key,
        }
    )


def test_human_and_agent_adapters_share_the_exact_contract() -> None:
    human = HumanAdapter(batch(0))
    agent = AgentAdapter(lambda _observation: batch(1).model_dump(mode="json", by_alias=True))

    assert human.command(observation(0)).expected_step == 7
    assert agent.command(observation(1)).expected_step == 7
    assert type(human.command(observation(0))) is type(agent.command(observation(1)))


def test_turn_keeps_actions_private_then_closes_simultaneously() -> None:
    now = [100.0]
    clock = TurnClock(
        monotonic=lambda: now[0],
        wall_time=lambda: datetime(2026, 7, 18, tzinfo=UTC),
    )
    turn = TurnCoordinator(clock)
    window = turn.open((observation(0), observation(1)))
    first = turn.submit(0, batch(0), received_at=window.monotonic_deadline)

    assert first.step == 7
    assert not hasattr(turn, "opponent_actions")
    with pytest.raises(CommandValidationError, match="turn.still_open"):
        turn.close()
    turn.submit(1, batch(1))
    assert turn.close() == ([[0, 1.2, 4]], [[1, 1.2, 4]])


@pytest.mark.parametrize(
    ("candidate", "slot", "code"),
    [
        (batch(0, step=6), 0, "command.replayed_step"),
        (batch(0, step=8), 0, "command.wrong_step"),
        (batch(1), 0, "command.source_not_owned"),
        (batch(0, ships=11), 0, "command.ship_budget_exceeded"),
    ],
)
def test_invalid_batches_have_stable_codes(candidate: CommandBatchV1, slot: int, code: str) -> None:
    turn = TurnCoordinator()
    turn.open((observation(0), observation(1)))
    with pytest.raises(CommandValidationError) as captured:
        turn.submit(slot, candidate)
    assert captured.value.code == code


def test_empty_action_late_submission_and_idempotent_replay() -> None:
    now = [50.0]
    turn = TurnCoordinator(TurnClock(monotonic=lambda: now[0]))
    window = turn.open((observation(0), observation(1)))
    accepted = turn.submit(0, batch(0))
    replay = turn.submit(0, batch(0))
    assert replay.command_hash == accepted.command_hash
    assert replay.idempotent_replay is True

    now[0] = window.monotonic_deadline + 0.001
    with pytest.raises(CommandValidationError) as captured:
        turn.submit(1, batch(1))
    assert captured.value.code == "command.late"
    assert turn.close() == ([[0, 1.2, 4]], [])


def test_duplicate_source_budget_is_aggregated_and_six_command_limit_is_contract_level() -> None:
    over_budget = CommandBatchV1.model_validate(
        {
            "schemaVersion": 1,
            "matchId": "match-1",
            "expectedStep": 7,
            "commands": [
                {"fromPlanetId": 0, "angle": 1.0, "ships": 6},
                {"fromPlanetId": 0, "angle": 2.0, "ships": 5},
            ],
            "idempotencyKey": "aggregate-001",
        }
    )
    turn = TurnCoordinator()
    turn.open((observation(0), observation(1)))
    with pytest.raises(CommandValidationError, match="command.ship_budget_exceeded"):
        turn.submit(0, over_budget)

    with pytest.raises(ValueError):
        CommandBatchV1.model_validate(
            {
                "schemaVersion": 1,
                "matchId": "match-1",
                "expectedStep": 7,
                "commands": [{"fromPlanetId": 0, "angle": 1.0, "ships": 1} for _ in range(7)],
                "idempotencyKey": "too-many-001",
            }
        )
