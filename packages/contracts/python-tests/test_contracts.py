import json
from pathlib import Path
from typing import Any

import pytest
from orbit_contracts.generate import SCHEMA_PATH, schema_text
from orbit_contracts.models import CommandBatchV1, ObservationV1
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def command_cases() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "command-batch-cases.json").read_text())


@pytest.mark.parametrize("test_case", command_cases(), ids=lambda case: case["name"])
def test_command_batch_cases_match_schema(test_case: dict[str, Any]) -> None:
    if test_case["valid"]:
        parsed = CommandBatchV1.model_validate(test_case["value"])
        assert parsed.model_dump(by_alias=True, mode="json") == test_case["value"]
    else:
        with pytest.raises(ValidationError):
            CommandBatchV1.model_validate(test_case["value"])


@pytest.mark.parametrize("angle", [float("nan"), float("inf"), float("-inf")])
def test_command_batch_rejects_non_finite_angles(angle: float) -> None:
    with pytest.raises(ValidationError):
        CommandBatchV1.model_validate(
            {
                "schemaVersion": 1,
                "matchId": "match_01",
                "expectedStep": 12,
                "commands": [{"fromPlanetId": 3, "angle": angle, "ships": 8}],
                "idempotencyKey": "turn-12-alpha",
            }
        )


def test_observation_rejects_hidden_seed() -> None:
    with pytest.raises(ValidationError):
        ObservationV1.model_validate(
            {
                "schemaVersion": 1,
                "matchId": "match_01",
                "step": 12,
                "player": 0,
                "deadlineAt": "2026-07-17T12:00:00Z",
                "angularVelocity": 0.01,
                "planets": [],
                "fleets": [],
                "initialPlanets": [],
                "comets": [],
                "seed": 42,
            }
        )


def test_committed_schema_matches_pydantic_source() -> None:
    assert SCHEMA_PATH.read_text() == schema_text()
