"""Per-participant Agent processes for authoritative accelerated matches."""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from orbit_agent_sandbox.launcher import SandboxLimits, docker_command
from orbit_agent_sandbox.runner import AgentRunner, RunnerSettings
from orbit_engine import EngineSnapshot
from orbit_runtime.observability import TraceContext, event_json

from orbit_match_worker.engine.runner import PlayerControllerError, PlayerViews
from orbit_match_worker.runtime.telemetry import worker_metrics

logger = logging.getLogger("orbit.worker")


@dataclass(frozen=True, slots=True)
class AgentTurnResponse:
    commands: list[list[int | float]]
    duration_ms: float
    logs_truncated: bool
    error_code: str | None = None


class AgentProcess(Protocol):
    def request(self, request_id: str, observation: dict[str, Any]) -> AgentTurnResponse: ...

    def close(self) -> None: ...


class LocalAgentProcess:
    """Test-only process boundary with the production protocol semantics."""

    def __init__(self, root: Path, entrypoint: str = "main.py:agent") -> None:
        self.runner = AgentRunner(
            RunnerSettings(strategy_root=root, entrypoint=entrypoint, timeout_seconds=0.05)
        )

    def request(self, request_id: str, observation: dict[str, Any]) -> AgentTurnResponse:
        response = self.runner.handle(
            {"type": "observe", "requestId": request_id, "observation": observation}
        )
        if response.get("type") != "action":
            return AgentTurnResponse([], 0, self.runner.logs.truncated, str(response.get("code")))
        duration = response.get("durationMs", 0)
        return AgentTurnResponse(
            commands=cast(list[list[int | float]], response["commands"]),
            duration_ms=float(duration) if isinstance(duration, (int, float)) else 0,
            logs_truncated=bool(response.get("logsTruncated", False)),
        )

    def close(self) -> None:
        return None


class DockerAgentProcess:
    def __init__(self, root: Path, image: str, entrypoint: str) -> None:
        self.name = f"orbit-match-agent-{uuid.uuid4().hex[:12]}"
        command = docker_command(
            root,
            image=image,
            entrypoint=entrypoint,
            limits=SandboxLimits(
                memory="768m" if "torch251" in image else "256m",
                timeout_seconds=1.0,
                max_log_bytes=64 * 1024,
            ),
            container_name=self.name,
        )
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        ready = self._read(timeout=8)
        if ready != {"type": "ready", "protocolVersion": 1}:
            self.close()
            raise RuntimeError("agent.load_failed")

    def request(self, request_id: str, observation: dict[str, Any]) -> AgentTurnResponse:
        if self.process.stdin is None:
            return AgentTurnResponse([], 0, False, "agent.crashed")
        try:
            self.process.stdin.write(
                json.dumps(
                    {"type": "observe", "requestId": request_id, "observation": observation},
                    separators=(",", ":"),
                )
                + "\n"
            )
            self.process.stdin.flush()
            response = self._read(timeout=2)
        except (BrokenPipeError, OSError, TimeoutError, ValueError):
            return AgentTurnResponse([], 0, False, "agent.crashed")
        if response.get("type") != "action":
            return AgentTurnResponse([], 0, False, str(response.get("code", "agent.exception")))
        return AgentTurnResponse(
            commands=cast(list[list[int | float]], response.get("commands", [])),
            duration_ms=float(response.get("durationMs", 0)),
            logs_truncated=bool(response.get("logsTruncated", False)),
        )

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        subprocess.run(
            ["docker", "rm", "--force", getattr(self, "name", "missing")],
            capture_output=True,
            check=False,
        )

    def _read(self, *, timeout: float) -> dict[str, Any]:
        if self.process.stdout is None:
            raise RuntimeError("agent.crashed")
        readable, _, _ = select.select([self.process.stdout], [], [], timeout)
        if not readable:
            raise TimeoutError
        line = self.process.stdout.readline()
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError
        return value


class ManagedAgent:
    def __init__(
        self,
        slot: int,
        process: AgentProcess,
        *,
        overage_budget_ms: float = 3000,
        soft_budget_ms: float = 250,
        max_consecutive_timeouts: int = 3,
    ) -> None:
        self.slot = slot
        self.process = process
        self.overage_budget_ms = overage_budget_ms
        self.soft_budget_ms = soft_budget_ms
        self.max_consecutive_timeouts = max_consecutive_timeouts
        self.overage_used_ms = 0.0
        self.consecutive_timeouts = 0
        self.logs_truncated = False

    def action(self, match_id: str, step: int, view: EngineSnapshot) -> list[list[int | float]]:
        request_id = f"{match_id}:{step}:{self.slot}"
        response = self.process.request(
            request_id,
            observation_payload(match_id, view, player=self.slot),
        )
        trace = TraceContext(
            request_id=request_id,
            match_id=match_id,
            step=step,
            sandbox_id=str(getattr(self.process, "name", f"slot-{self.slot}")),
        )
        worker_metrics.add("turn_latency_ms", response.duration_ms, controller="agent")
        worker_metrics.add("sandbox_cpu_ms", response.duration_ms, slot=str(self.slot))
        if response.error_code is not None:
            worker_metrics.add("sandbox_crash_total", code=response.error_code)
        logger.info(
            event_json(
                "agent.turn",
                trace,
                durationMs=response.duration_ms,
                logsTruncated=response.logs_truncated,
                errorCode=response.error_code,
            )
        )
        self.logs_truncated = self.logs_truncated or response.logs_truncated
        self.overage_used_ms += max(0, response.duration_ms - self.soft_budget_ms)
        if self.overage_used_ms > self.overage_budget_ms:
            raise PlayerControllerError(self.slot, "agent.overage_exhausted")
        if response.error_code == "agent.timeout":
            self.consecutive_timeouts += 1
            if self.consecutive_timeouts >= self.max_consecutive_timeouts:
                raise PlayerControllerError(self.slot, "agent.consecutive_timeouts")
            return []
        if response.error_code is not None:
            raise PlayerControllerError(self.slot, response.error_code)
        self.consecutive_timeouts = 0
        return response.commands

    def close(self) -> None:
        self.process.close()


class AgentMatchProvider:
    """Runs Agent-v-Agent without wall-clock turn sleeps while preserving every step."""

    def __init__(self, match_id: str, agents: tuple[ManagedAgent, ManagedAgent]) -> None:
        self.match_id = match_id
        self.agents = agents

    def __call__(self, step: int, views: PlayerViews) -> tuple[object, object]:
        return (
            self.agents[0].action(self.match_id, step, views[0]),
            self.agents[1].action(self.match_id, step, views[1]),
        )

    def close(self) -> None:
        for agent in self.agents:
            agent.close()


class HumanAgentProvider:
    def __init__(
        self,
        match_id: str,
        agent: ManagedAgent,
        human_slot: int,
        human_action: Any,
    ) -> None:
        self.match_id = match_id
        self.agent = agent
        self.human_slot = human_slot
        self.human_action = human_action

    def __call__(self, step: int, views: PlayerViews) -> tuple[object, object]:
        actions: list[object] = [[], []]
        actions[self.human_slot] = self.human_action(step, views[self.human_slot])
        agent_slot = 1 - self.human_slot
        actions[agent_slot] = self.agent.action(self.match_id, step, views[agent_slot])
        return actions[0], actions[1]


def observation_payload(match_id: str, snapshot: EngineSnapshot, *, player: int) -> dict[str, Any]:
    deadline = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=snapshot.step * 3 + 3)
    return {
        "schemaVersion": 1,
        "matchId": match_id,
        "step": snapshot.step,
        "player": player,
        "deadlineAt": deadline.isoformat().replace("+00:00", "Z"),
        "angularVelocity": snapshot.angular_velocity,
        "planets": [
            {
                "id": planet.id,
                "owner": planet.owner,
                "x": planet.x,
                "y": planet.y,
                "radius": planet.radius,
                "ships": planet.ships,
                "production": planet.production,
            }
            for planet in snapshot.planets
        ],
        "fleets": [
            {
                "id": fleet.id,
                "owner": fleet.owner,
                "x": fleet.x,
                "y": fleet.y,
                "angle": fleet.angle,
                "fromPlanetId": fleet.from_planet_id,
                "ships": fleet.ships,
            }
            for fleet in snapshot.fleets
        ],
        "initialPlanets": [
            {
                "id": planet.id,
                "owner": planet.owner,
                "x": planet.x,
                "y": planet.y,
                "radius": planet.radius,
                "ships": planet.ships,
                "production": planet.production,
            }
            for planet in snapshot.initial_planets
        ],
        "comets": [],
    }
