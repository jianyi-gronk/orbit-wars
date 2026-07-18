import pytest
from orbit_match_worker import app
from orbit_match_worker.app import service_name


def test_service_name() -> None:
    assert service_name() == "match-worker"


def test_dependency_health_uses_shared_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"postgres": "ok", "redis": "ok", "object_storage": "ok"}
    monkeypatch.setattr(app, "check_dependencies", lambda: expected)

    assert app.dependency_health() == expected
