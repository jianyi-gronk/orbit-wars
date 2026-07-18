import pytest
from fastapi import HTTPException
from orbit_api import main
from orbit_api.main import app, health
from orbit_runtime.infrastructure import DependencyCheckFailed


def test_api_metadata_and_health() -> None:
    assert app.title == "Orbit Wars API"
    assert health() == {"status": "ok", "service": "api"}


def test_dependency_health_reports_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "check_dependencies",
        lambda: {"postgres": "ok", "redis": "ok", "object_storage": "ok"},
    )

    assert main.dependency_health() == {
        "status": "ok",
        "dependencies": {"postgres": "ok", "redis": "ok", "object_storage": "ok"},
    }


def test_dependency_health_hides_connection_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> dict[str, str]:
        raise DependencyCheckFailed({"postgres": "OperationalError"})

    monkeypatch.setattr(main, "check_dependencies", fail)

    with pytest.raises(HTTPException) as raised:
        main.dependency_health()

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "status": "unavailable",
        "dependencies": {"postgres": "OperationalError"},
    }
