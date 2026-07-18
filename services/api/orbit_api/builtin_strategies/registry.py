"""Deterministic package builder and metadata for built-in strategies."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).parent
_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class BuiltinStrategy:
    slug: str
    title: str
    entrypoint: str
    runtime_image: str
    source_files: tuple[tuple[Path, str], ...]

    def package_bytes(self) -> bytes:
        manifest = {
            "schemaVersion": 1,
            "entrypoint": self.entrypoint,
            "builtin": self.slug,
        }
        files = [("manifest.json", json.dumps(manifest, separators=(",", ":")).encode())]
        files.extend((target, source.read_bytes()) for source, target in self.source_files)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for target, content in sorted(files):
                info = zipfile.ZipInfo(target, date_time=_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100444 << 16
                archive.writestr(info, content)
        return output.getvalue()

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.package_bytes()).hexdigest()


def _python_files(directory: str) -> tuple[tuple[Path, str], ...]:
    root = _ROOT / directory
    return tuple(
        (path, path.relative_to(root).as_posix())
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


BASIC = BuiltinStrategy(
    slug="basic-v1",
    title="Signal Cadet",
    entrypoint="main.py:agent",
    runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
    source_files=((_ROOT / "basic.py", "main.py"),),
)
TRAINING = BuiltinStrategy(
    slug="training-v1",
    title="Quiet Vector",
    entrypoint="main.py:agent",
    runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
    source_files=((_ROOT / "training.py", "main.py"),),
)
EXPERT_V69 = BuiltinStrategy(
    slug="expert-v69",
    title="Producer v69",
    entrypoint="entrypoint.py:agent",
    runtime_image="orbit-agent-sandbox:py311-torch251-v1",
    source_files=_python_files("expert_v69"),
)
KAGGLE_STRUCTURED_V11 = BuiltinStrategy(
    slug="kaggle-structured-v11",
    title="Kaggle Structured v11",
    entrypoint="entrypoint.py:agent",
    runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
    source_files=_python_files("kaggle_structured_v11"),
)
ALL_BUILTINS = (BASIC, TRAINING, EXPERT_V69, KAGGLE_STRUCTURED_V11)
