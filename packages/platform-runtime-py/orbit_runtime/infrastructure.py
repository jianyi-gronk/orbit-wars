"""Runtime configuration and dependency readiness probes."""

from collections.abc import Callable
from dataclasses import dataclass
from os import environ

import boto3  # type: ignore[import-untyped]
import psycopg
from botocore.config import Config  # type: ignore[import-untyped]
from redis import Redis


@dataclass(frozen=True)
class InfrastructureSettings:
    """Connection settings injected into API and worker processes."""

    database_url: str
    redis_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    s3_bucket: str

    @classmethod
    def from_environment(cls) -> "InfrastructureSettings":
        """Read local-safe defaults while allowing deployment injection."""
        return cls(
            database_url=environ.get(
                "DATABASE_URL",
                "postgresql://orbit_wars:local_postgres_password@localhost:5432/orbit_wars",
            ),
            redis_url=environ.get("REDIS_URL", "redis://localhost:6379/0"),
            s3_endpoint_url=environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
            s3_access_key=environ.get("S3_ACCESS_KEY", "orbit_wars_local"),
            s3_secret_key=environ.get("S3_SECRET_KEY", "local_object_storage_secret"),
            s3_region=environ.get("S3_REGION", "us-east-1"),
            s3_bucket=environ.get("S3_BUCKET", "orbit-wars-local"),
        )


class DependencyCheckFailed(RuntimeError):
    """Raised when one or more required infrastructure services are unavailable."""

    def __init__(self, failures: dict[str, str]) -> None:
        super().__init__("one or more infrastructure dependencies are unavailable")
        self.failures = failures


def _check_postgres(settings: InfrastructureSettings) -> None:
    with psycopg.connect(settings.database_url, connect_timeout=2) as connection:
        connection.execute("SELECT 1").fetchone()


def _check_redis(settings: InfrastructureSettings) -> None:
    with Redis.from_url(settings.redis_url, socket_connect_timeout=2) as client:
        if not client.ping():
            raise RuntimeError("PING returned a false response")


def _check_object_storage(settings: InfrastructureSettings) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 0}),
    )
    client.list_buckets()


def check_dependencies(
    settings: InfrastructureSettings | None = None,
    probes: tuple[tuple[str, Callable[[InfrastructureSettings], None]], ...] | None = None,
) -> dict[str, str]:
    """Verify all required services without leaking connection details."""
    active_settings = settings or InfrastructureSettings.from_environment()
    active_probes = probes or (
        ("postgres", _check_postgres),
        ("redis", _check_redis),
        ("object_storage", _check_object_storage),
    )
    failures: dict[str, str] = {}
    statuses: dict[str, str] = {}

    for name, probe in active_probes:
        try:
            probe(active_settings)
            statuses[name] = "ok"
        except Exception as error:  # dependency clients expose unrelated error hierarchies
            failures[name] = type(error).__name__

    if failures:
        raise DependencyCheckFailed(failures)

    return statuses
