"""Safe strategy extraction and deterministic validation pipeline."""

from __future__ import annotations

import hashlib
import io
import json
import os
import select as io_select
import stat
import subprocess
import tempfile
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from orbit_agent_sandbox.launcher import SandboxLimits, docker_command
from orbit_agent_sandbox.runner import (
    AgentLoadError,
    AgentRunner,
    AgentTimeoutError,
    RunnerSettings,
)
from orbit_engine import OrbitEngine
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.builtin_strategies.basic import agent as basic_agent
from orbit_api.db.base import utc_now
from orbit_api.db.models import StrategyStatus, StrategyVersion
from orbit_api.domain.strategy_versions import StrategyPackageInvalidError, inspect_package
from orbit_api.storage.strategy_packages import StrategyPackageStore

MAX_FILES = 128
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
FIXED_MATCH_STEPS = 24
FIXED_MATCH_SEED = 20260718


class StrategyValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class StrategyValidationUnavailable(RuntimeError):
    pass


class SandboxSession(Protocol):
    def action(self, observation: dict[str, Any]) -> list[list[int | float]]: ...

    def close(self) -> None: ...


SandboxFactory = Callable[[Path, str, str], SandboxSession]


@dataclass(frozen=True)
class ValidationReport:
    result: str
    checks: tuple[str, ...]
    fixed_steps: int

    def as_json(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "checks": list(self.checks),
            "fixedSteps": self.fixed_steps,
        }


class LocalSandboxSession:
    """Test-only runner using the same protocol implementation without Docker."""

    def __init__(self, root: Path, _image: str, entrypoint: str) -> None:
        try:
            self.runner = AgentRunner(
                RunnerSettings(strategy_root=root, entrypoint=entrypoint, timeout_seconds=0.5)
            )
        except AgentTimeoutError as error:
            raise StrategyValidationError(
                "agent.import_timeout",
                _safe_agent_message("agent.import_timeout"),
            ) from error
        except AgentLoadError as error:
            raise StrategyValidationError(
                "agent.load_failed",
                _safe_agent_message("agent.load_failed"),
            ) from error
        self.counter = 0

    def action(self, observation: dict[str, Any]) -> list[list[int | float]]:
        self.counter += 1
        response = self.runner.handle(
            {
                "type": "observe",
                "requestId": f"validation-{self.counter}",
                "observation": observation,
            }
        )
        if response.get("type") != "action":
            code = str(response.get("code", "agent.exception"))
            raise StrategyValidationError(code, _safe_agent_message(code))
        return response["commands"]  # type: ignore[return-value]

    def close(self) -> None:
        return None


class DockerSandboxSession:
    def __init__(self, root: Path, image: str, entrypoint: str) -> None:
        self.name = f"orbit-validation-{uuid.uuid4().hex[:12]}"
        command = docker_command(
            root,
            image=image,
            entrypoint=entrypoint,
            limits=SandboxLimits(
                memory="768m" if "torch251" in image else "256m",
                timeout_seconds=1.0,
            ),
            container_name=self.name,
        )
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
            )
            ready = self._read_message(timeout=8.0)
        except (OSError, TimeoutError, json.JSONDecodeError) as error:
            self.close()
            raise StrategyValidationUnavailable("sandbox could not start") from error
        if ready != {"type": "ready", "protocolVersion": 1}:
            self.close()
            raise StrategyValidationError(
                "agent.load_failed",
                "The strategy entrypoint could not be imported in its fixed runtime.",
            )
        self.counter = 0

    def action(self, observation: dict[str, Any]) -> list[list[int | float]]:
        if self.process.stdin is None:
            raise StrategyValidationUnavailable("sandbox input is unavailable")
        self.counter += 1
        message = {
            "type": "observe",
            "requestId": f"validation-{self.counter}",
            "observation": observation,
        }
        try:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            response = self._read_message(timeout=3.0)
        except (BrokenPipeError, OSError, TimeoutError, json.JSONDecodeError) as error:
            raise StrategyValidationUnavailable("sandbox stopped during validation") from error
        if response.get("type") != "action":
            code = str(response.get("code", "agent.exception"))
            raise StrategyValidationError(code, _safe_agent_message(code))
        commands = response.get("commands")
        if not isinstance(commands, list):
            raise StrategyValidationError(
                "agent.invalid_action", _safe_agent_message("agent.invalid_action")
            )
        return commands

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None:
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

    def _read_message(self, *, timeout: float) -> dict[str, Any]:
        if self.process.stdout is None:
            raise StrategyValidationUnavailable("sandbox output is unavailable")
        readable, _, _ = io_select.select([self.process.stdout], [], [], timeout)
        if not readable:
            raise TimeoutError("sandbox response deadline expired")
        line = self.process.stdout.readline()
        if not line:
            raise StrategyValidationUnavailable("sandbox exited without a response")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise json.JSONDecodeError("response is not an object", line, 0)
        return value


def safe_extract(package: bytes, destination: Path) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(package))
    except zipfile.BadZipFile as error:
        raise StrategyValidationError(
            "package.invalid_zip", "The package is not a readable ZIP."
        ) from error
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise StrategyValidationError(
                "package.too_many_files", "The package contains too many files."
            )
        seen: set[str] = set()
        total_size = 0
        for entry in entries:
            path = PurePosixPath(entry.filename)
            normalized = path.as_posix()
            if (
                not normalized
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or normalized.casefold() in seen
            ):
                raise StrategyValidationError(
                    "package.unsafe_path", "The package contains an unsafe path."
                )
            seen.add(normalized.casefold())
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise StrategyValidationError("package.symlink", "Symbolic links are not allowed.")
            if entry.is_dir():
                continue
            total_size += entry.file_size
            ratio = entry.file_size / max(1, entry.compress_size)
            if entry.file_size > MAX_FILE_BYTES or total_size > MAX_UNCOMPRESSED_BYTES:
                raise StrategyValidationError(
                    "package.too_large", "The unpacked package is too large."
                )
            if ratio > MAX_COMPRESSION_RATIO:
                raise StrategyValidationError(
                    "package.compression_ratio", "The package has an unsafe compression ratio."
                )
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
            target.chmod(0o444)


def validate_package(
    package: bytes,
    *,
    runtime_image: str,
    sandbox_factory: SandboxFactory = DockerSandboxSession,
) -> ValidationReport:
    try:
        manifest = inspect_package(package)
    except StrategyPackageInvalidError as error:
        raise StrategyValidationError(
            "package.invalid_manifest",
            "The package manifest is missing or invalid.",
        ) from error
    entrypoint = str(manifest["entrypoint"])
    with tempfile.TemporaryDirectory(prefix="orbit-strategy-") as temporary:
        root = Path(temporary)
        safe_extract(package, root)
        root.chmod(0o755)
        try:
            sandbox = sandbox_factory(root, runtime_image, entrypoint)
        except StrategyValidationError:
            raise
        except Exception as error:
            raise StrategyValidationUnavailable("sandbox startup failed") from error
        engine = OrbitEngine()
        snapshot = engine.reset(seed=FIXED_MATCH_SEED)
        completed_steps = 0
        try:
            for _ in range(FIXED_MATCH_STEPS):
                candidate_observation = observation_payload(snapshot, player=0)
                baseline_observation = observation_payload(snapshot, player=1)
                candidate = sandbox.action(candidate_observation)
                baseline = basic_agent(baseline_observation)
                try:
                    result = engine.step_raw([candidate, baseline])
                except (TypeError, ValueError) as error:
                    raise StrategyValidationError(
                        "agent.invalid_action",
                        "The strategy returned a command that the fixed ruleset rejected.",
                    ) from error
                snapshot = result.snapshot
                completed_steps += 1
                if result.done:
                    break
        finally:
            sandbox.close()
    return ValidationReport(
        result="ready",
        checks=("safe_extract", "import", "contract", "resources", "fixed_match"),
        fixed_steps=completed_steps,
    )


def validate_strategy_version(
    session: Session,
    store: StrategyPackageStore,
    public_id: str,
    *,
    sandbox_factory: SandboxFactory = DockerSandboxSession,
) -> StrategyVersion:
    version = session.scalar(select(StrategyVersion).where(StrategyVersion.public_id == public_id))
    if version is None:
        raise StrategyValidationError("strategy.not_found", "The strategy version was not found.")
    if version.status not in {StrategyStatus.UPLOADED, StrategyStatus.VALIDATING}:
        raise StrategyValidationError(
            "strategy.not_validatable",
            "Only uploaded or interrupted validating versions can be validated.",
        )
    version.status = StrategyStatus.VALIDATING
    session.commit()
    package = store.get(version.object_key)
    if hashlib.sha256(package).hexdigest() != version.content_hash:
        error = StrategyValidationError(
            "package.checksum_mismatch",
            "The stored package no longer matches its immutable checksum.",
        )
        _reject(session, version, error)
        return version
    try:
        report = validate_package(
            package,
            runtime_image=version.runtime_image,
            sandbox_factory=sandbox_factory,
        )
    except StrategyValidationError as error:
        _reject(session, version, error)
        return version
    version.status = StrategyStatus.READY
    version.validation_report = report.as_json()
    version.validated_at = utc_now()
    session.commit()
    session.refresh(version)
    return version


def observation_payload(snapshot: Any, *, player: int) -> dict[str, Any]:
    deadline = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=snapshot.step * 3 + 3)
    return {
        "schemaVersion": 1,
        "matchId": "strategy-validation",
        "step": snapshot.step,
        "player": player,
        "deadlineAt": deadline.isoformat().replace("+00:00", "Z"),
        "angularVelocity": snapshot.angular_velocity,
        "planets": [_planet_payload(planet) for planet in snapshot.planets],
        "fleets": [_fleet_payload(fleet) for fleet in snapshot.fleets],
        "initialPlanets": [_planet_payload(planet) for planet in snapshot.initial_planets],
        "comets": [],
    }


def _planet_payload(planet: Any) -> dict[str, Any]:
    return {
        "id": planet.id,
        "owner": planet.owner,
        "x": planet.x,
        "y": planet.y,
        "radius": planet.radius,
        "ships": planet.ships,
        "production": planet.production,
    }


def _fleet_payload(fleet: Any) -> dict[str, Any]:
    return {
        "id": fleet.id,
        "owner": fleet.owner,
        "x": fleet.x,
        "y": fleet.y,
        "angle": fleet.angle,
        "fromPlanetId": fleet.from_planet_id,
        "ships": fleet.ships,
    }


def _reject(session: Session, version: StrategyVersion, error: StrategyValidationError) -> None:
    version.status = StrategyStatus.REJECTED
    version.validation_report = {
        "result": "rejected",
        "code": error.code,
        "message": error.safe_message,
    }
    version.validated_at = utc_now()
    session.commit()
    session.refresh(version)


def _safe_agent_message(code: str) -> str:
    messages = {
        "agent.timeout": "The strategy exceeded the per-turn time limit.",
        "agent.invalid_action": "The strategy returned an invalid command list.",
        "agent.load_failed": "The strategy entrypoint could not be imported.",
        "agent.import_timeout": "The strategy took too long to import.",
    }
    return messages.get(code, "The strategy raised an error during its fixed validation match.")
