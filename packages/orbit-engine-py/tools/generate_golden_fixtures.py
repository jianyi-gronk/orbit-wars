"""Generate compact golden fixtures from the pinned Kaggle oracle.

Run this with the audited orbit-wars project's Python environment, not the
platform's production environment:

  /path/to/orbit-wars/.venv/bin/python tools/generate_golden_fixtures.py \
    --orbit-project /path/to/orbit-wars --output-dir /tmp/orbit-goldens
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

RULESET_ID = "orbit-wars-2p-v1"
UPSTREAM_COMMIT = "462efa26dd3d11018cde2b9e9ce9245b91cef471"
FLOAT_DECIMAL_PLACES = 9
FLOAT_ABS_TOLERANCE = 1e-9


def normalize(value: Any) -> Any:
    if isinstance(value, float):
        normalized = round(value, FLOAT_DECIMAL_PLACES)
        return 0.0 if normalized == 0 else normalized
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, tuple):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        normalize(value),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def commitment(seed: int) -> str:
    return hashlib.sha256(f"{RULESET_ID}:{seed}".encode()).hexdigest()


def planet_rows(value: list[list[int | float]]) -> list[list[int | float]]:
    return [
        [
            int(row[0]),
            int(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            int(row[5]),
            int(row[6]),
        ]
        for row in value
    ]


def fleet_rows(value: list[list[int | float]]) -> list[list[int | float]]:
    return [
        [
            int(row[0]),
            int(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
            int(row[5]),
            int(row[6]),
        ]
        for row in value
    ]


def build_fixture(case_id: str, source: dict[str, str], replay: dict[str, Any]) -> dict[str, Any]:
    seed = int(replay["info"]["seed"])
    steps = replay["steps"]
    frames: list[dict[str, Any]] = []
    actions: list[list[Any]] = []

    for index, frame in enumerate(steps):
        observation = frame[0]["observation"]
        rewards = [state.get("reward") for state in frame]
        done = all(state.get("status") == "DONE" for state in frame)
        planets = planet_rows(observation.get("planets", []))
        fleets = fleet_rows(observation.get("fleets", []))
        state_payload = {
            "ruleset_id": RULESET_ID,
            "config": {
                "episode_steps": 500,
                "ship_speed": 6.0,
                "comet_speed": 4.0,
            },
            "step": index,
            "done": done,
            "angular_velocity": observation["angular_velocity"],
            "planets": planets,
            "fleets": fleets,
            "initial_planets": planet_rows(observation["initial_planets"]),
            "next_fleet_id": observation["next_fleet_id"],
            "comets": observation.get("comets", []),
            "comet_planet_ids": observation.get("comet_planet_ids", []),
            "rewards": rewards,
            "seed_commitment": commitment(seed),
        }
        frames.append(
            {
                "step": index,
                "planets_sha256": fingerprint(planets),
                "fleets_sha256": fingerprint(fleets),
                "state_hash": fingerprint(state_payload),
                "planet_count": len(planets),
                "fleet_count": len(fleets),
                "rewards": rewards,
                "done": done,
            }
        )
        if index > 0:
            actions.append([state.get("action") or [] for state in frame])

    final_frame = frames[-1]
    return {
        "schema_version": 1,
        "case_id": case_id,
        "ruleset_id": RULESET_ID,
        "seed": seed,
        "source": source,
        "oracle": {
            "distribution": "kaggle-environments 1.30.1",
            "commit": UPSTREAM_COMMIT,
        },
        "generation_platform": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "float_abs_tolerance": FLOAT_ABS_TOLERANCE,
        "actions": actions,
        "frames": frames,
        "expected_end_step": final_frame["step"] if final_frame["done"] else None,
        "expected_rewards": final_frame["rewards"] if final_frame["done"] else None,
    }


def write_fixture(output_dir: Path, fixture: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{fixture['case_id']}.json"
    path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    print(path)


def generate(orbit_project: Path, output_dir: Path) -> None:
    sys.path.insert(0, str(orbit_project))
    from kaggle_environments import make

    fixed = make("orbit_wars", configuration={"seed": 1_234_567}, debug=True)
    fixed.reset()
    for _ in range(55):
        fixed.step([[], []])
    write_fixture(
        output_dir,
        build_fixture(
            "fixed-seed-1234567-empty-55",
            {"kind": "fixed-seed", "description": "55 empty turns including first comet spawn"},
            fixed.toJSON(),
        ),
    )

    historical_path = orbit_project / "notes/replays/2026-06-15/79969550.json"
    historical = json.loads(historical_path.read_text())
    write_fixture(
        output_dir,
        build_fixture(
            "history-79969550",
            {"kind": "historical-replay", "path": "notes/replays/2026-06-15/79969550.json"},
            historical,
        ),
    )

    v69 = make("orbit_wars", configuration={"seed": 6}, debug=True)
    v69.run(
        [
            str(orbit_project / "submissions/producer/v69/main.py"),
            str(orbit_project / "agents/pool/orbit_wars_exp34.py"),
        ]
    )
    write_fixture(
        output_dir,
        build_fixture(
            "v69-vs-exp34-seed6",
            {
                "kind": "representative-v69-match",
                "player_0": "submissions/producer/v69/main.py",
                "player_1": "agents/pool/orbit_wars_exp34.py",
            },
            v69.toJSON(),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orbit-project", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    generate(args.orbit_project.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
