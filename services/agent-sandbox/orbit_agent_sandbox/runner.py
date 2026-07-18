"""Versioned JSONL runner for one untrusted Orbit Wars agent process."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import os
import resource
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, BinaryIO, TextIO, cast

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_COMMANDS = 6


def service_name() -> str:
    """Return the stable component name used by operations tooling."""
    return "agent-sandbox"


class AgentLoadError(RuntimeError):
    pass


class AgentTimeoutError(RuntimeError):
    pass


class InvalidAgentActionError(ValueError):
    pass


@dataclass(frozen=True)
class RunnerSettings:
    strategy_root: Path
    entrypoint: str = "main.py:agent"
    import_timeout_seconds: float = 8.0
    timeout_seconds: float = 1.0
    max_log_bytes: int = 64 * 1024

    @classmethod
    def from_environment(cls) -> RunnerSettings:
        return cls(
            strategy_root=Path(os.environ.get("ORBIT_AGENT_ROOT", "/strategy")),
            entrypoint=os.environ.get("ORBIT_AGENT_ENTRYPOINT", "main.py:agent"),
            import_timeout_seconds=float(
                os.environ.get("ORBIT_AGENT_IMPORT_TIMEOUT_SECONDS", "8.0")
            ),
            timeout_seconds=float(os.environ.get("ORBIT_AGENT_TIMEOUT_SECONDS", "1.0")),
            max_log_bytes=int(os.environ.get("ORBIT_AGENT_MAX_LOG_BYTES", str(64 * 1024))),
        )


class BoundedLog(io.TextIOBase):
    def __init__(self, maximum_bytes: int) -> None:
        self.maximum_bytes = maximum_bytes
        self.size = 0
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        encoded_size = len(value.encode("utf-8", errors="replace"))
        remaining = max(0, self.maximum_bytes - self.size)
        self.size += min(encoded_size, remaining)
        if encoded_size > remaining:
            self.truncated = True
        return len(value)


class _Deadline:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.previous_handler: Any = None
        self.enabled = False

    def __enter__(self) -> None:
        if self.seconds <= 0:
            raise AgentTimeoutError("agent deadline expired")
        if threading.current_thread() is not threading.main_thread():
            return
        self.enabled = True
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self._expired)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)

    def __exit__(self, *_args: object) -> None:
        if not self.enabled:
            return
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)

    @staticmethod
    def _expired(_signum: int, _frame: object) -> None:
        raise AgentTimeoutError("agent deadline expired")


class AgentRunner:
    def __init__(self, settings: RunnerSettings) -> None:
        self.settings = settings
        self.logs = BoundedLog(settings.max_log_bytes)
        self.agent = self._load_agent()

    def _load_agent(self) -> Callable[[dict[str, Any]], object]:
        file_name, separator, function_name = self.settings.entrypoint.partition(":")
        if not separator or not file_name.endswith(".py") or not function_name.isidentifier():
            raise AgentLoadError("entrypoint must use path.py:function syntax")

        root = self.settings.strategy_root.resolve()
        module_path = (root / file_name).resolve()
        if not module_path.is_relative_to(root) or not module_path.is_file():
            raise AgentLoadError("entrypoint is outside the strategy package")

        spec = importlib.util.spec_from_file_location("orbit_user_strategy", module_path)
        if spec is None or spec.loader is None:
            raise AgentLoadError("entrypoint module cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        previous_path = list(sys.path)
        sys.path.insert(0, str(root))
        try:
            with (
                _Deadline(self.settings.import_timeout_seconds),
                contextlib.redirect_stdout(self.logs),
                contextlib.redirect_stderr(self.logs),
            ):
                spec.loader.exec_module(module)
        except AgentTimeoutError:
            raise
        except BaseException as error:
            raise AgentLoadError("entrypoint module raised during import") from error
        finally:
            sys.path[:] = previous_path
        return _agent_function(module, function_name)

    def handle(self, request: object) -> dict[str, object]:
        request_id: str | None = None
        try:
            request_id, observation = _validate_request(request)
            started = time.monotonic()
            with (
                _Deadline(self.settings.timeout_seconds),
                contextlib.redirect_stdout(self.logs),
                contextlib.redirect_stderr(self.logs),
            ):
                action = self.agent(observation)
            commands = validate_action(action)
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            return {
                "type": "action",
                "requestId": request_id,
                "commands": commands,
                "durationMs": elapsed_ms,
                "logsTruncated": self.logs.truncated,
            }
        except AgentTimeoutError:
            return _error_response(request_id, "agent.timeout", recoverable=False)
        except InvalidAgentActionError:
            return _error_response(request_id, "agent.invalid_action", recoverable=False)
        except (TypeError, ValueError, KeyError):
            return _error_response(request_id, "protocol.invalid_request", recoverable=True)
        except BaseException:
            return _error_response(request_id, "agent.exception", recoverable=False)


def run_stream(
    input_stream: BinaryIO,
    output_stream: TextIO,
    runner: AgentRunner,
) -> None:
    _write_message(
        output_stream,
        {"type": "ready", "protocolVersion": PROTOCOL_VERSION},
    )
    while True:
        line = input_stream.readline(MAX_REQUEST_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
            _write_message(
                output_stream,
                _error_response(None, "protocol.request_too_large", recoverable=True),
            )
            if not line.endswith(b"\n"):
                _discard_line(input_stream)
            continue
        try:
            request = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _error_response(None, "protocol.invalid_json", recoverable=True)
        else:
            response = runner.handle(request)
        _write_message(output_stream, response)


def validate_action(value: object) -> list[list[int | float]]:
    if not isinstance(value, list) or len(value) > MAX_COMMANDS:
        raise InvalidAgentActionError("action must be a list of at most six commands")
    validated: list[list[int | float]] = []
    for command in value:
        if not isinstance(command, (list, tuple)) or len(command) != 3:
            raise InvalidAgentActionError("each command must have three values")
        planet_id, angle, ships = command
        if isinstance(planet_id, bool) or not isinstance(planet_id, int) or planet_id < 0:
            raise InvalidAgentActionError("planet id must be a non-negative integer")
        if isinstance(angle, bool) or not isinstance(angle, (int, float)):
            raise InvalidAgentActionError("angle must be finite")
        normalized_angle = float(angle)
        if not math.isfinite(normalized_angle):
            raise InvalidAgentActionError("angle must be finite")
        if isinstance(ships, bool) or not isinstance(ships, int) or ships <= 0:
            raise InvalidAgentActionError("ships must be a positive integer")
        validated.append([planet_id, normalized_angle, ships])
    return validated


def apply_process_limits() -> None:
    """Apply defense-in-depth limits in addition to Docker runtime controls."""
    limits = (
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_FSIZE, 1024 * 1024),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_NPROC, 32),
    )
    for kind, maximum in limits:
        try:
            _, hard = resource.getrlimit(kind)
            resource.setrlimit(kind, (min(maximum, hard), min(maximum, hard)))
        except (OSError, ValueError):
            continue


def main() -> int:
    apply_process_limits()
    try:
        runner = AgentRunner(RunnerSettings.from_environment())
    except AgentTimeoutError:
        _write_message(
            sys.stdout,
            {"type": "fatal", "code": "agent.import_timeout", "recoverable": False},
        )
        return 1
    except AgentLoadError:
        _write_message(
            sys.stdout,
            {"type": "fatal", "code": "agent.load_failed", "recoverable": False},
        )
        return 1
    run_stream(sys.stdin.buffer, sys.stdout, runner)
    return 0


def _agent_function(module: ModuleType, function_name: str) -> Callable[[dict[str, Any]], object]:
    function = getattr(module, function_name, None)
    if not callable(function):
        raise AgentLoadError("entrypoint function is missing")
    return cast(Callable[[dict[str, Any]], object], function)


def _validate_request(request: object) -> tuple[str, dict[str, Any]]:
    if not isinstance(request, dict) or request.get("type") != "observe":
        raise ValueError("request type must be observe")
    request_id = request.get("requestId")
    observation = request.get("observation")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ValueError("requestId must be a non-empty string")
    if not isinstance(observation, dict):
        raise ValueError("observation must be an object")
    return request_id, observation


def _error_response(
    request_id: str | None,
    code: str,
    *,
    recoverable: bool,
) -> dict[str, object]:
    return {
        "type": "error",
        "requestId": request_id,
        "code": code,
        "recoverable": recoverable,
    }


def _write_message(output: TextIO, message: dict[str, object]) -> None:
    output.write(json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n")
    output.flush()


def _discard_line(input_stream: BinaryIO) -> None:
    while True:
        chunk = input_stream.readline(MAX_REQUEST_BYTES + 1)
        if not chunk or chunk.endswith(b"\n"):
            return


if __name__ == "__main__":
    raise SystemExit(main())
