import io
import json
from pathlib import Path

import pytest
from orbit_agent_sandbox.launcher import SandboxLimits, docker_command
from orbit_agent_sandbox.runner import (
    AgentLoadError,
    AgentRunner,
    RunnerSettings,
    run_stream,
    service_name,
    validate_action,
)


def write_agent(root: Path, source: str) -> None:
    (root / "main.py").write_text(source)


def request_line(request_id: str = "request-1") -> bytes:
    return (
        json.dumps(
            {
                "type": "observe",
                "requestId": request_id,
                "observation": {"step": 0, "player": 0},
            }
        ).encode()
        + b"\n"
    )


def responses(output: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def test_service_name() -> None:
    assert service_name() == "agent-sandbox"


def test_runner_loads_agent_and_uses_versioned_jsonl(tmp_path: Path) -> None:
    write_agent(tmp_path, "def agent(obs):\n    return [[3, 1.25, 7]]\n")
    runner = AgentRunner(RunnerSettings(strategy_root=tmp_path))
    output = io.StringIO()

    run_stream(io.BytesIO(request_line()), output, runner)

    ready, action = responses(output)
    assert ready == {"type": "ready", "protocolVersion": 1}
    assert action["type"] == "action"
    assert action["requestId"] == "request-1"
    assert action["commands"] == [[3, 1.25, 7]]
    assert action["logsTruncated"] is False


def test_agent_stdout_cannot_corrupt_protocol_and_is_bounded(tmp_path: Path) -> None:
    write_agent(
        tmp_path,
        "def agent(obs):\n    print('private-log-' * 10000)\n    return []\n",
    )
    runner = AgentRunner(RunnerSettings(strategy_root=tmp_path, max_log_bytes=128))
    output = io.StringIO()

    run_stream(io.BytesIO(request_line()), output, runner)

    ready, action = responses(output)
    assert ready["type"] == "ready"
    assert action["type"] == "action"
    assert action["logsTruncated"] is True
    assert "private-log" not in output.getvalue()
    assert runner.logs.size == 128


def test_timeout_and_exception_return_safe_categories(tmp_path: Path) -> None:
    write_agent(
        tmp_path,
        "def agent(obs):\n    while True:\n        pass\n",
    )
    timeout_runner = AgentRunner(RunnerSettings(strategy_root=tmp_path, timeout_seconds=0.02))
    timeout = timeout_runner.handle({"type": "observe", "requestId": "slow", "observation": {}})
    write_agent(
        tmp_path,
        "def agent(obs):\n    raise RuntimeError('platform-secret-123')\n",
    )
    exception_runner = AgentRunner(RunnerSettings(strategy_root=tmp_path))
    exception = exception_runner.handle(
        {"type": "observe", "requestId": "broken", "observation": {}}
    )

    assert timeout == {
        "type": "error",
        "requestId": "slow",
        "code": "agent.timeout",
        "recoverable": False,
    }
    assert exception == {
        "type": "error",
        "requestId": "broken",
        "code": "agent.exception",
        "recoverable": False,
    }
    assert "platform-secret-123" not in json.dumps(exception)


@pytest.mark.parametrize(
    "action",
    [
        "not-a-list",
        [[1, 0.5]],
        [[-1, 0.5, 2]],
        [[1, float("nan"), 2]],
        [[1, 0.5, 0]],
        [[1, 0.5, 1]] * 7,
    ],
)
def test_invalid_agent_actions_are_rejected(action: object) -> None:
    with pytest.raises(ValueError):
        validate_action(action)


def test_malformed_requests_do_not_stop_following_requests(tmp_path: Path) -> None:
    write_agent(tmp_path, "def agent(obs):\n    return []\n")
    runner = AgentRunner(RunnerSettings(strategy_root=tmp_path))
    input_stream = io.BytesIO(b"not-json\n" + request_line("valid-after-error"))
    output = io.StringIO()

    run_stream(input_stream, output, runner)

    ready, invalid, valid = responses(output)
    assert ready["type"] == "ready"
    assert invalid["code"] == "protocol.invalid_json"
    assert valid["type"] == "action"
    assert valid["requestId"] == "valid-after-error"


def test_entrypoint_cannot_escape_strategy_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def agent(obs): return []\n")

    with pytest.raises(AgentLoadError):
        AgentRunner(RunnerSettings(strategy_root=tmp_path, entrypoint="../outside.py:agent"))


def test_docker_command_enforces_isolation_without_host_environment(
    tmp_path: Path,
) -> None:
    command = docker_command(
        tmp_path,
        image="orbit-agent-sandbox:py311-stdlib-v1",
        limits=SandboxLimits(
            memory="128m",
            cpus="0.5",
            pids=16,
            tmpfs_size="8m",
        ),
        container_name="sandbox-test",
    )

    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--user=65532:65532" in command
    assert "--pids-limit=16" in command
    assert "--memory=128m" in command
    assert "--memory-swap=128m" in command
    assert "--cpus=0.5" in command
    assert "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777" in command
    assert f"--mount=type=bind,src={tmp_path.resolve()},dst=/strategy,readonly" in command
    assert "--name=sandbox-test" in command
    assert all("SECRET" not in argument for argument in command)
