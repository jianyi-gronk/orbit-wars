#!/usr/bin/env python3
"""Extract an audited submission.py assembled by Kaggle notebook writefile cells."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_KERNEL = "pilkwang/orbit-wars-structured-baseline"


def _cell_source(cell: dict[str, object]) -> str:
    raw = cell.get("source", "")
    if isinstance(raw, list):
        return "".join(str(part) for part in raw)
    return str(raw)


def extract(notebook_path: Path) -> bytes:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    chunks: list[str] = []
    for cell in notebook.get("cells", []):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = _cell_source(cell)
        first, separator, rest = source.partition("\n")
        if first not in {
            "%%writefile submission.py",
            "%%writefile -a submission.py",
        }:
            continue
        if not separator:
            raise ValueError("writefile cell has no source body")
        chunks.append(rest)
    if not chunks or "def agent(" not in chunks[-1]:
        raise ValueError("notebook does not contain a complete submission agent")
    return "".join(chunks).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if metadata.get("id") != EXPECTED_KERNEL or metadata.get("is_private") is not False:
        raise ValueError("unexpected or private Kaggle kernel")

    content = extract(args.notebook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(
        json.dumps(
            {
                "kernel": EXPECTED_KERNEL,
                "notebookSha256": hashlib.sha256(args.notebook.read_bytes()).hexdigest(),
                "sourceSha256": hashlib.sha256(content).hexdigest(),
                "sourceBytes": len(content),
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
