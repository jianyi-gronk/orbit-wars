from __future__ import annotations

import pytest
from orbit_match_worker.engine import (
    MatchStateMachine,
    MatchStatus,
    PlatformFailure,
    PlayerForfeit,
    TransitionError,
)


def test_happy_path_records_ordered_transitions() -> None:
    machine = MatchStateMachine()

    for status in (
        MatchStatus.PREPARING,
        MatchStatus.READY,
        MatchStatus.RUNNING,
        MatchStatus.FINALIZING,
        MatchStatus.FINISHED,
    ):
        machine.transition(status)

    assert machine.status is MatchStatus.FINISHED
    assert [record.sequence for record in machine.history] == list(range(5))
    assert [record.current for record in machine.history] == [
        MatchStatus.PREPARING,
        MatchStatus.READY,
        MatchStatus.RUNNING,
        MatchStatus.FINALIZING,
        MatchStatus.FINISHED,
    ]


def test_illegal_transition_is_rejected_without_mutating_state() -> None:
    machine = MatchStateMachine()

    with pytest.raises(TransitionError, match="cannot transition"):
        machine.transition(MatchStatus.RUNNING)

    assert machine.status is MatchStatus.QUEUED
    assert machine.history == ()


def test_failure_statuses_require_the_correct_domain_cause() -> None:
    machine = MatchStateMachine()
    machine.transition(MatchStatus.PREPARING)
    machine.transition(MatchStatus.READY)
    machine.transition(MatchStatus.RUNNING)

    with pytest.raises(TransitionError, match="platform failure"):
        machine.transition(MatchStatus.FAILED, cause=PlayerForfeit(slot=0, code="timeout"))
    with pytest.raises(TransitionError, match="player forfeit"):
        machine.transition(
            MatchStatus.FORFEITED,
            cause=PlatformFailure(code="redis.unavailable"),
        )

    assert machine.status is MatchStatus.RUNNING
