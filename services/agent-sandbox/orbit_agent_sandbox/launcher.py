"""Hardened Docker invocation for one extracted strategy package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxLimits:
    memory: str = "256m"
    cpus: str = "1.0"
    pids: int = 32
    tmpfs_size: str = "16m"
    import_timeout_seconds: float = 8.0
    timeout_seconds: float = 1.0
    max_log_bytes: int = 64 * 1024


DEFAULT_LIMITS = SandboxLimits()


def docker_command(
    strategy_root: Path,
    *,
    image: str,
    entrypoint: str = "main.py:agent",
    limits: SandboxLimits = DEFAULT_LIMITS,
    container_name: str | None = None,
) -> list[str]:
    root = strategy_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("strategy root must be a directory")
    if not image or any(character.isspace() for character in image):
        raise ValueError("sandbox image must be a non-empty image reference")

    command = [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65532:65532",
        f"--pids-limit={limits.pids}",
        f"--memory={limits.memory}",
        f"--memory-swap={limits.memory}",
        f"--cpus={limits.cpus}",
        "--ulimit=nofile=64:64",
        "--ulimit=fsize=1024:1024",
        f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={limits.tmpfs_size},mode=1777",
        "--workdir=/strategy",
        "--env=HOME=/tmp",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        f"--env=ORBIT_AGENT_ENTRYPOINT={entrypoint}",
        f"--env=ORBIT_AGENT_IMPORT_TIMEOUT_SECONDS={limits.import_timeout_seconds}",
        f"--env=ORBIT_AGENT_TIMEOUT_SECONDS={limits.timeout_seconds}",
        f"--env=ORBIT_AGENT_MAX_LOG_BYTES={limits.max_log_bytes}",
        f"--mount=type=bind,src={root},dst=/strategy,readonly",
    ]
    if container_name is not None:
        command.append(f"--name={container_name}")
    command.append(image)
    return command
