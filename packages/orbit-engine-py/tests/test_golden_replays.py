from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from orbit_engine import OrbitEngine
from orbit_engine.hashing import FLOAT_ABS_TOLERANCE, normalize_for_hash

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))


def fingerprint(value: Any) -> str:
    encoded = json.dumps(
        normalize_for_hash(value),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def assert_field(case_id: str, step: int, field: str, actual: object, expected: object) -> None:
    assert actual == expected, (
        f"golden mismatch: case={case_id} step={step} field={field} "
        f"expected={expected!r} actual={actual!r}"
    )


def run_fixture(fixture: dict[str, Any]) -> list[str]:
    case_id = fixture["case_id"]
    assert fixture["float_abs_tolerance"] == FLOAT_ABS_TOLERANCE
    engine = OrbitEngine()
    snapshot = engine.reset(seed=fixture["seed"])
    state_hashes: list[str] = []

    for expected in fixture["frames"]:
        step = expected["step"]
        if step > 0:
            result = engine.step_raw(fixture["actions"][step - 1])
            snapshot = result.snapshot

        planets = [planet.to_row() for planet in snapshot.planets]
        fleets = [fleet.to_row() for fleet in snapshot.fleets]
        assert_field(case_id, step, "planets", fingerprint(planets), expected["planets_sha256"])
        assert_field(case_id, step, "fleets", fingerprint(fleets), expected["fleets_sha256"])
        assert_field(case_id, step, "planet_count", len(planets), expected["planet_count"])
        assert_field(case_id, step, "fleet_count", len(fleets), expected["fleet_count"])
        assert_field(case_id, step, "rewards", list(snapshot.rewards), expected["rewards"])
        assert_field(case_id, step, "done", snapshot.done, expected["done"])
        assert_field(case_id, step, "state_hash", snapshot.state_hash, expected["state_hash"])
        state_hashes.append(snapshot.state_hash)

    expected_end_step = fixture["expected_end_step"]
    if expected_end_step is None:
        assert not engine.done
    else:
        assert engine.done
        assert snapshot.step == expected_end_step
        assert list(snapshot.rewards) == fixture["expected_rewards"]
    return state_hashes


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem)
def test_golden_replay_matches_oracle_step_by_step(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text())

    assert run_fixture(fixture) == run_fixture(fixture)


def test_golden_suite_contains_all_required_sources() -> None:
    fixtures = [json.loads(path.read_text()) for path in FIXTURE_PATHS]
    source_kinds = {fixture["source"]["kind"] for fixture in fixtures}

    assert len(fixtures) == 3
    assert source_kinds == {"fixed-seed", "historical-replay", "representative-v69-match"}
