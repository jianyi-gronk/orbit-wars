"""Streaming gzip replay writer with checkpoint and delta records."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from orbit_engine import EngineSnapshot

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ReplayArtifactInfo:
    path: Path
    checksum: str
    size_bytes: int
    frame_count: int
    checkpoint_count: int


class ReplayObjectStore(Protocol):
    def put_immutable(self, key: str, content: bytes) -> object: ...


def _snapshot_payload(snapshot: EngineSnapshot) -> dict[str, Any]:
    return {
        "step": snapshot.step,
        "stateHash": snapshot.state_hash,
        "planets": [planet.to_row() for planet in snapshot.planets],
        "fleets": [fleet.to_row() for fleet in snapshot.fleets],
        "rewards": list(snapshot.rewards),
    }


def _delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {
        "step": current["step"],
        "stateHash": current["stateHash"],
    }
    for field in ("planets", "fleets", "rewards"):
        if current[field] != previous[field]:
            changed[field] = current[field]
    return changed


class ReplayStreamWriter:
    def __init__(
        self,
        path: Path,
        *,
        match: dict[str, Any],
        participants: list[dict[str, Any]],
        checkpoint_interval: int = 20,
    ) -> None:
        self.path = path
        self.checkpoint_interval = checkpoint_interval
        self.frame_count = 0
        self.checkpoint_count = 0
        self._previous: dict[str, Any] | None = None
        self._closed = False
        path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = gzip.open(  # noqa: SIM115 - closed explicitly by finalize()
            path, "wt", encoding="utf-8", newline="\n"
        )
        self._write(
            {
                "type": "header",
                "schemaVersion": SCHEMA_VERSION,
                "match": _public_match_metadata(match),
                "participants": [_public_participant(value) for value in participants],
            }
        )

    def append(
        self,
        snapshot: EngineSnapshot,
        commands: tuple[object, object] | list[object],
    ) -> None:
        if self._closed:
            raise RuntimeError("replay writer is closed")
        current = _snapshot_payload(snapshot)
        checkpoint = self._previous is None or snapshot.step % self.checkpoint_interval == 0
        record: dict[str, Any]
        if checkpoint:
            record = {"type": "checkpoint", "frame": current}
            self.checkpoint_count += 1
        else:
            assert self._previous is not None
            record = {"type": "delta", "frame": _delta(self._previous, current)}
        record["commands"] = commands
        self._write(record)
        self._previous = current
        self.frame_count += 1

    def finalize(self, result: dict[str, Any]) -> ReplayArtifactInfo:
        if self._closed:
            raise RuntimeError("replay writer is already closed")
        self._write({"type": "result", "result": _public_result(result)})
        self._stream.close()
        self._closed = True
        content = self.path.read_bytes()
        return ReplayArtifactInfo(
            path=self.path,
            checksum=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            frame_count=self.frame_count,
            checkpoint_count=self.checkpoint_count,
        )

    def upload(self, store: ReplayObjectStore, key: str, info: ReplayArtifactInfo) -> None:
        content = info.path.read_bytes()
        if hashlib.sha256(content).hexdigest() != info.checksum:
            raise RuntimeError("replay checksum changed before upload")
        store.put_immutable(key, content)

    def _write(self, value: dict[str, Any]) -> None:
        self._stream.write(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")
        self._stream.flush()


def _public_match_metadata(value: dict[str, Any]) -> dict[str, Any]:
    fields = ("publicId", "rulesetId", "engineCommit", "seed", "mapId", "mode")
    return {field: value[field] for field in fields if field in value}


def _public_participant(value: dict[str, Any]) -> dict[str, Any]:
    fields = ("fleetPublicId", "fleetName", "slot", "controllerType", "strategyVersionId")
    return {field: value[field] for field in fields if field in value}


def _public_result(value: dict[str, Any]) -> dict[str, Any]:
    fields = ("winnerSlot", "reason", "finalStep", "endedAt")
    return {field: value[field] for field in fields if field in value}
