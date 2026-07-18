from __future__ import annotations

from pathlib import Path

import pytest
from orbit_engine import PINNED_RULESET_ID
from orbit_match_worker.engine import MatchRunner, MatchSpec, MatchStatus
from orbit_match_worker.runtime import (
    AgentMatchProvider,
    AgentTurnResponse,
    HumanAgentProvider,
    LocalAgentProcess,
    ManagedAgent,
)


def agent(root: Path, source: str) -> LocalAgentProcess:
    root.mkdir()
    (root / "main.py").write_text(source)
    return LocalAgentProcess(root)


def test_agent_vs_agent_runs_accelerated_with_isolated_processes(tmp_path: Path) -> None:
    first_process = agent(tmp_path / "first", "def agent(obs):\n    return []\n")
    second_process = agent(tmp_path / "second", "def agent(obs):\n    return []\n")
    provider = AgentMatchProvider(
        "match-agent-agent",
        (ManagedAgent(0, first_process), ManagedAgent(1, second_process)),
    )
    try:
        result = MatchRunner(MatchSpec("match-agent-agent", PINNED_RULESET_ID, seed=31)).run(
            provider
        )
    finally:
        provider.close()

    assert first_process is not second_process
    assert result.status is MatchStatus.FINISHED
    assert result.outcome is not None
    assert result.outcome.final_step == 499
    assert len(result.commands) == 998


def test_human_vs_agent_uses_each_slots_private_view(tmp_path: Path) -> None:
    process = agent(
        tmp_path / "agent",
        "def agent(obs):\n    assert obs['player'] == 1\n    return []\n",
    )
    provider = HumanAgentProvider(
        "match-human-agent",
        ManagedAgent(1, process),
        human_slot=0,
        human_action=lambda _step, _view: [],
    )
    result = MatchRunner(MatchSpec("match-human-agent", PINNED_RULESET_ID, seed=32)).run(provider)

    assert result.status is MatchStatus.FINISHED
    assert result.failure is None


class FailingProcess:
    def __init__(self, responses: list[AgentTurnResponse]) -> None:
        self.responses = iter(responses)
        self.requests: list[str] = []

    def request(self, request_id, observation):
        self.requests.append(request_id)
        assert observation["step"] >= 0
        return next(self.responses)

    def close(self):
        return None


def test_consecutive_timeouts_forfeit_and_request_ids_are_step_scoped() -> None:
    process = FailingProcess(
        [AgentTurnResponse([], 1000, False, "agent.timeout") for _ in range(3)]
    )
    managed = ManagedAgent(0, process, overage_budget_ms=10_000)
    from orbit_engine import OrbitEngine

    snapshot = OrbitEngine().reset(seed=7)
    assert managed.action("match-x", 0, snapshot) == []
    assert managed.action("match-x", 1, snapshot) == []
    with pytest.raises(Exception, match="agent.consecutive_timeouts"):
        managed.action("match-x", 2, snapshot)
    assert process.requests == ["match-x:0:0", "match-x:1:0", "match-x:2:0"]


def test_crash_and_overage_are_attributed_to_agent_slot() -> None:
    from orbit_engine import OrbitEngine
    from orbit_match_worker.engine import PlayerControllerError

    snapshot = OrbitEngine().reset(seed=8)
    crashed = ManagedAgent(1, FailingProcess([AgentTurnResponse([], 0, True, "agent.exception")]))
    with pytest.raises(PlayerControllerError) as crash:
        crashed.action("match-y", 0, snapshot)
    assert crash.value.slot == 1
    assert crash.value.code == "agent.exception"
    assert crashed.logs_truncated is True

    over = ManagedAgent(
        0,
        FailingProcess([AgentTurnResponse([], 400, False)]),
        overage_budget_ms=100,
        soft_budget_ms=250,
    )
    with pytest.raises(PlayerControllerError, match="agent.overage_exhausted"):
        over.action("match-z", 0, snapshot)
