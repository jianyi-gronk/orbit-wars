"""Match worker process metadata."""

from orbit_match_worker.infrastructure import check_dependencies


def service_name() -> str:
    """Return the stable component name used by operations tooling."""
    return "match-worker"


def dependency_health() -> dict[str, str]:
    """Report whether required stateful services are reachable."""
    return check_dependencies()
