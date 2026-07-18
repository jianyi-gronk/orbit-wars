"""Generate or verify committed JSON Schema artifacts."""

import argparse
import json
from pathlib import Path

from orbit_contracts.models import ContractsV1

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "contracts-v1.json"


def _remove_openapi_keywords(value: object) -> None:
    """Keep emitted artifacts valid under strict JSON Schema 2020-12 tooling."""
    if isinstance(value, dict):
        value.pop("discriminator", None)
        for nested in value.values():
            _remove_openapi_keywords(nested)
    elif isinstance(value, list):
        for nested in value:
            _remove_openapi_keywords(nested)


def schema_text() -> str:
    schema = ContractsV1.model_json_schema(by_alias=True, mode="serialization")
    _remove_openapi_keywords(schema)
    schema["$id"] = "https://schemas.orbit-wars.example/contracts-v1.json"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = schema_text()

    if args.check:
        if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text() != expected:
            raise SystemExit("contracts-v1.json is stale; run `pnpm contracts:generate`")
        return

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(expected)


if __name__ == "__main__":
    main()
