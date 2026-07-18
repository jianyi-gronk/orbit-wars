from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]


def test_license_notice_and_upstream_checksums_are_auditable() -> None:
    license_text = (PACKAGE_ROOT / "LICENSE").read_text()
    notice = (PACKAGE_ROOT / "NOTICE").read_text()
    provenance = (PACKAGE_ROOT / "PROVENANCE.md").read_text()

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "462efa26dd3d11018cde2b9e9ce9245b91cef471" in notice
    assert "3f78c1a9064644a7789d9aa464aa83770071d42023716213d223887b8ca267f4" in provenance
    assert "8d8a2b6c0b092f40ea5f4c381328788a402dfcbd7a1bd8ed5f1c3e1eb5f079d1" in provenance


def test_pinned_runtime_has_no_kaggle_import() -> None:
    engine_sources = [path.read_text() for path in (PACKAGE_ROOT / "orbit_engine").glob("*.py")]

    assert all("import kaggle_environments" not in source for source in engine_sources)
    assert all("from kaggle_environments" not in source for source in engine_sources)
