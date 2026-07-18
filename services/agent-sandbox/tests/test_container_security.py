import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from orbit_agent_sandbox.launcher import SandboxLimits, docker_command

IMAGE = "orbit-agent-sandbox:py311-stdlib-v1"
RUN_DOCKER_TESTS = os.environ.get("ORBIT_RUN_DOCKER_TESTS") == "1"


def container_available() -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not RUN_DOCKER_TESTS or not container_available(),
    reason="set ORBIT_RUN_DOCKER_TESTS=1 after building the sandbox image",
)


def invoke_container(
    strategy_root: Path,
    source: str,
    *,
    timeout_seconds: float = 1.0,
) -> tuple[int, list[dict[str, object]], str]:
    (strategy_root / "main.py").write_text(source)
    name = f"orbit-sandbox-test-{uuid.uuid4().hex[:10]}"
    command = docker_command(
        strategy_root,
        image=IMAGE,
        limits=SandboxLimits(timeout_seconds=timeout_seconds, pids=16, memory="128m"),
        container_name=name,
    )
    request = json.dumps(
        {
            "type": "observe",
            "requestId": "security-check",
            "observation": {"step": 0, "player": 0},
        }
    )
    environment = {**os.environ, "ORBIT_PLATFORM_SECRET": "must-not-enter-container"}
    try:
        result = subprocess.run(
            command,
            input=request + "\n",
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
            env=environment,
        )
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            capture_output=True,
            check=False,
        )
    messages = [json.loads(line) for line in result.stdout.splitlines()]
    return result.returncode, messages, result.stderr


def test_container_blocks_network_host_files_credentials_and_root_writes(
    tmp_path: Path,
) -> None:
    source = """
import os
import socket

def agent(obs):
    assert os.getuid() == 65532
    assert "ORBIT_PLATFORM_SECRET" not in os.environ
    assert not os.path.exists("/host-probe/platform-secret")
    try:
        open("/root-write-proof", "w").write("forbidden")
        raise RuntimeError("root filesystem was writable")
    except OSError:
        pass
    try:
        open("/strategy/package-mutation", "w").write("forbidden")
        raise RuntimeError("strategy package was writable")
    except OSError:
        pass
    with open("/tmp/allowed", "w") as handle:
        handle.write("tmpfs")
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=0.2)
        raise RuntimeError("network was reachable")
    except OSError:
        pass
    memory_limit = int(open("/sys/fs/cgroup/memory.max").read())
    pids_limit = int(open("/sys/fs/cgroup/pids.max").read())
    assert memory_limit <= 128 * 1024 * 1024
    assert pids_limit <= 16
    return []
"""

    return_code, messages, stderr = invoke_container(tmp_path, source)

    assert return_code == 0, stderr
    assert messages[0] == {"type": "ready", "protocolVersion": 1}
    assert messages[1]["type"] == "action"
    assert messages[1]["commands"] == []


def test_container_caps_processes_and_agent_logs(tmp_path: Path) -> None:
    source = """
import subprocess

def agent(obs):
    print("x" * 1_000_000)
    children = []
    limited = False
    for _ in range(100):
        try:
            children.append(subprocess.Popen(["sleep", "2"]))
        except OSError:
            limited = True
            break
    for child in children:
        child.terminate()
    assert limited
    return []
"""

    return_code, messages, stderr = invoke_container(tmp_path, source)

    assert return_code == 0, stderr
    assert messages[1]["type"] == "action"
    assert messages[1]["logsTruncated"] is True
    assert len(json.dumps(messages)) < 1024


def test_container_terminates_cpu_timeout_without_a_traceback(tmp_path: Path) -> None:
    source = """
def agent(obs):
    while True:
        pass
"""

    return_code, messages, stderr = invoke_container(
        tmp_path,
        source,
        timeout_seconds=0.05,
    )

    assert return_code == 0, stderr
    assert messages[1] == {
        "type": "error",
        "requestId": "security-check",
        "code": "agent.timeout",
        "recoverable": False,
    }
    assert "Traceback" not in stderr
