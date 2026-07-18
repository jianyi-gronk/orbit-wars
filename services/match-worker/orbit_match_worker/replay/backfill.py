"""Rebuild replay streams from retained authoritative Redis frame events."""

from __future__ import annotations

import gzip
import hashlib
import json
from typing import Any


def build_replay_content(
    *,
    match: dict[str, Any],
    participants: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    result: dict[str, Any],
) -> tuple[bytes, int]:
    if not frames:
        raise ValueError("cannot backfill a replay without authoritative frames")
    normalized = [_frame_payload(frame, result) for frame in frames]
    if normalized[0]["step"] != 0:
        normalized.insert(0, {**normalized[0], "step": 0})
    records: list[dict[str, Any]] = [
        {
            "type": "header",
            "schemaVersion": 1,
            "match": match,
            "participants": participants,
        }
    ]
    for frame in normalized:
        records.append(
            {
                "type": "checkpoint" if frame["step"] % 20 == 0 else "delta",
                "frame": frame,
                "commands": [[], []],
            }
        )
    records.append({"type": "result", "result": result})
    encoded = (
        "\n".join(json.dumps(item, separators=(",", ":")) for item in records) + "\n"
    ).encode()
    return gzip.compress(encoded, mtime=0), len(normalized)


def _frame_payload(frame: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    step = int(frame["step"])
    planets = [
        [
            planet["id"],
            planet["owner"],
            planet["x"],
            planet["y"],
            planet["radius"],
            planet["ships"],
            planet["production"],
        ]
        for planet in frame.get("planets", [])
    ]
    fleets = [
        [
            fleet["id"],
            fleet["owner"],
            fleet["x"],
            fleet["y"],
            fleet["angle"],
            fleet["fromPlanetId"],
            fleet["ships"],
        ]
        for fleet in frame.get("fleets", [])
    ]
    digest = hashlib.sha256(
        json.dumps([step, planets, fleets], separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    rewards = result.get("rewards", [0, 0]) if step == result.get("finalStep") else [0, 0]
    return {
        "step": step,
        "stateHash": digest,
        "planets": planets,
        "fleets": fleets,
        "rewards": rewards,
    }
