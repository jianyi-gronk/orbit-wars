import io
import zipfile

import pytest
from orbit_api.domain.strategy_source import (
    MAX_SOURCE_BYTES,
    build_source_package,
    guided_source,
    platform_basic_source,
)
from orbit_api.domain.strategy_versions import StrategyPackageInvalidError, inspect_package


def test_source_package_is_deterministic_and_uses_fixed_entrypoint() -> None:
    first = build_source_package(platform_basic_source())
    second = build_source_package(platform_basic_source())

    assert first.content == second.content
    assert first.content_hash == second.content_hash
    assert inspect_package(first.content)["entrypoint"] == "main.py:agent"
    with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
        assert set(archive.namelist()) == {"main.py", "manifest.json"}


def test_source_package_rejects_empty_oversized_and_nul_source() -> None:
    for source in ("", "x" * (MAX_SOURCE_BYTES + 1), "print('x')\x00"):
        with pytest.raises(StrategyPackageInvalidError):
            build_source_package(source)


def test_guided_source_clamps_parameters_and_changes_target_mode() -> None:
    source = guided_source(3, -4, "weakest")

    assert "LAUNCH_RATIO = 0.90" in source
    assert "MINIMUM_SHIPS = 1" in source
    assert 'TARGET_PREFERENCE = "weakest"' in source
    assert 'float(planet.get("ships", 0))' in source
