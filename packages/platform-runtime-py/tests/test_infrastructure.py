import pytest
from orbit_runtime.infrastructure import (
    DependencyCheckFailed,
    InfrastructureSettings,
    check_dependencies,
)


def settings() -> InfrastructureSettings:
    return InfrastructureSettings(
        database_url="postgresql://local",
        redis_url="redis://local",
        s3_endpoint_url="http://local",
        s3_access_key="local",
        s3_secret_key="local",
        s3_region="us-east-1",
        s3_bucket="orbit-wars-local",
    )


def test_dependency_probe_reports_all_services() -> None:
    def ready(_: InfrastructureSettings) -> None:
        return None

    probes = (("postgres", ready), ("redis", ready), ("object_storage", ready))

    assert check_dependencies(settings(), probes) == {
        "postgres": "ok",
        "redis": "ok",
        "object_storage": "ok",
    }


def test_dependency_probe_aggregates_safe_error_types() -> None:
    def unavailable(_: InfrastructureSettings) -> None:
        raise ConnectionError("secret connection string")

    with pytest.raises(DependencyCheckFailed) as raised:
        check_dependencies(settings(), (("postgres", unavailable),))

    assert raised.value.failures == {"postgres": "ConnectionError"}
    assert "secret connection string" not in str(raised.value)
