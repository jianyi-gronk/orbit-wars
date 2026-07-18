from __future__ import annotations

from orbit_engine import PINNED_RULESET_ID
from orbit_match_worker.engine import (
    MatchRunner,
    MatchSpec,
    MatchStatus,
    PlatformFailure,
    PlayerControllerError,
    PlayerForfeit,
)


def noop_provider(step: int, views: object) -> tuple[object, object]:
    del step, views
    return ([], [])


def test_fixed_script_match_runs_to_deterministic_completion() -> None:
    spec = MatchSpec(
        match_id="match_deterministic",
        ruleset_id=PINNED_RULESET_ID,
        seed=202_607_17,
    )

    first = MatchRunner(spec).run(noop_provider)
    second = MatchRunner(spec).run(noop_provider)

    assert first.status is MatchStatus.FINISHED
    assert first.spec.ruleset_id == PINNED_RULESET_ID
    assert first.spec.seed == 202_607_17
    assert first.spec.slots == (0, 1)
    assert first.outcome is not None
    assert first.outcome.reason == "step_limit"
    assert first.outcome.final_step == 499
    assert len(first.frames) == 500
    assert len(first.commands) == 998
    assert [frame.step for frame in first.frames] == list(range(500))
    assert [(command.step, command.slot) for command in first.commands[:4]] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    ]
    assert first.frames[-1].state_hash == second.frames[-1].state_hash
    assert [frame.state_hash for frame in first.frames] == [
        frame.state_hash for frame in second.frames
    ]
    assert all(record.payload == () for record in first.commands)
    assert all(len(record.command_hash) == 64 for record in first.commands)
    assert [transition.current for transition in first.transitions] == [
        MatchStatus.PREPARING,
        MatchStatus.READY,
        MatchStatus.RUNNING,
        MatchStatus.FINALIZING,
        MatchStatus.FINISHED,
    ]


def test_player_failure_forfeits_and_finishes_without_platform_failure() -> None:
    spec = MatchSpec("match_forfeit", PINNED_RULESET_ID, seed=7)

    def failing_player(step: int, views: object) -> tuple[object, object]:
        del step, views
        raise PlayerControllerError(slot=1, code="controller.crashed")

    result = MatchRunner(spec).run(failing_player)

    assert result.status is MatchStatus.FINISHED
    assert result.outcome is not None
    assert result.outcome.winner_slot == 0
    assert result.outcome.reason == "forfeit"
    assert result.outcome.rewards == (1, -1)
    assert isinstance(result.failure, PlayerForfeit)
    assert not isinstance(result.failure, PlatformFailure)
    assert MatchStatus.FORFEITED in [transition.current for transition in result.transitions]
    assert MatchStatus.FAILED not in [transition.current for transition in result.transitions]


def test_unexpected_provider_failure_is_platform_failed_and_unscored() -> None:
    spec = MatchSpec("match_platform_failure", PINNED_RULESET_ID, seed=8)

    def broken_platform(step: int, views: object) -> tuple[object, object]:
        del step, views
        raise RuntimeError("queue disappeared")

    result = MatchRunner(spec).run(broken_platform)

    assert result.status is MatchStatus.FAILED
    assert result.outcome is None
    assert isinstance(result.failure, PlatformFailure)
    assert result.failure.code == "platform.execution_error"
    assert [transition.current for transition in result.transitions][-1] is MatchStatus.FAILED
    assert MatchStatus.FORFEITED not in [transition.current for transition in result.transitions]


def test_invalid_action_is_attributed_to_the_submitting_player() -> None:
    spec = MatchSpec("match_invalid_action", PINNED_RULESET_ID, seed=9)

    def invalid_action(step: int, views: object) -> tuple[object, object]:
        del step, views
        return ([], [[0, float("nan"), 1]])

    result = MatchRunner(spec).run(invalid_action)

    assert result.status is MatchStatus.FINISHED
    assert result.outcome is not None
    assert result.outcome.winner_slot == 0
    assert isinstance(result.failure, PlayerForfeit)
    assert result.failure.slot == 1
    assert result.failure.code == "controller.invalid_action"
