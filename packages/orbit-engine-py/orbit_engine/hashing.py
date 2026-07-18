"""Canonical state hashing for replay and recovery verification."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from orbit_engine.schema import EngineSnapshot

FLOAT_DECIMAL_PLACES = 9
FLOAT_ABS_TOLERANCE = 1e-9


def normalize_for_hash(value: Any) -> Any:
    """Normalize floats so hashes survive insignificant libm/platform drift."""

    if isinstance(value, float):
        normalized = round(value, FLOAT_DECIMAL_PLACES)
        return 0.0 if normalized == 0 else normalized
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_for_hash(item) for key, item in value.items()}
    return value


def seed_commitment(ruleset_id: str, seed: int) -> str:
    material = f"{ruleset_id}:{seed}".encode()
    return hashlib.sha256(material).hexdigest()


def state_payload(snapshot: EngineSnapshot) -> dict[str, Any]:
    """Build the player-neutral authoritative payload used for hashing."""

    return {
        "ruleset_id": snapshot.ruleset_id,
        "config": {
            "episode_steps": snapshot.config.episode_steps,
            "ship_speed": snapshot.config.ship_speed,
            "comet_speed": snapshot.config.comet_speed,
        },
        "step": snapshot.step,
        "done": snapshot.done,
        "angular_velocity": snapshot.angular_velocity,
        "planets": [planet.to_row() for planet in snapshot.planets],
        "fleets": [fleet.to_row() for fleet in snapshot.fleets],
        "initial_planets": [planet.to_row() for planet in snapshot.initial_planets],
        "next_fleet_id": snapshot.next_fleet_id,
        "comets": [
            {
                "planet_ids": list(group.planet_ids),
                "paths": [[list(point) for point in path] for path in group.paths],
                "path_index": group.path_index,
            }
            for group in snapshot.comets
        ],
        "comet_planet_ids": list(snapshot.comet_planet_ids),
        "rewards": list(snapshot.rewards),
        "seed_commitment": snapshot.seed_commitment,
    }


def state_hash(snapshot: EngineSnapshot) -> str:
    encoded = json.dumps(
        normalize_for_hash(state_payload(snapshot)),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
