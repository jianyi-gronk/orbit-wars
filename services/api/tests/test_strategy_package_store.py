from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from orbit_api.storage.strategy_packages import (
    S3StrategyPackageStore,
    StrategyPackageStoreError,
)
from orbit_runtime.infrastructure import InfrastructureSettings


class FakeS3Client:
    def __init__(self) -> None:
        self.bucket_exists = False
        self.objects: dict[str, dict[str, Any]] = {}
        self.put_calls = 0

    def head_bucket(self, *, Bucket: str) -> None:
        if not self.bucket_exists:
            raise client_error("404", "HeadBucket")

    def create_bucket(self, *, Bucket: str) -> None:
        self.bucket_exists = True

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise client_error("NoSuchKey", "HeadObject")
        value = self.objects[Key]
        return {
            "ContentLength": len(value["Body"]),
            "Metadata": value["Metadata"],
        }

    def put_object(self, *, Bucket: str, Key: str, **values: Any) -> None:
        self.put_calls += 1
        if Key in self.objects:
            raise client_error("PreconditionFailed", "PutObject")
        self.objects[Key] = values

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop(Key, None)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise client_error("NoSuchKey", "GetObject")
        return {"Body": BytesIO(self.objects[Key]["Body"])}


def client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def settings() -> InfrastructureSettings:
    return InfrastructureSettings(
        database_url="postgresql://local",
        redis_url="redis://local",
        s3_endpoint_url="http://local",
        s3_access_key="local",
        s3_secret_key="local",
        s3_region="us-east-1",
        s3_bucket="strategies",
    )


def test_s3_store_creates_bucket_and_never_overwrites() -> None:
    client = FakeS3Client()
    store = S3StrategyPackageStore(settings(), client=client)  # type: ignore[arg-type]
    content = b"immutable-package"

    store.ensure_bucket()
    first = store.put_immutable("fleet/version.zip", content)
    repeated = store.put_immutable("fleet/version.zip", content)

    assert client.bucket_exists is True
    assert first.created is True
    assert repeated.created is False
    assert client.put_calls == 1


def test_s3_store_rejects_existing_key_with_other_content() -> None:
    client = FakeS3Client()
    store = S3StrategyPackageStore(settings(), client=client)  # type: ignore[arg-type]
    store.put_immutable("fleet/version.zip", b"first")
    client.objects["fleet/version.zip"]["Body"] = b"tampered"

    with pytest.raises(StrategyPackageStoreError):
        store.put_immutable("fleet/version.zip", b"first")


def test_s3_store_delete_is_idempotent() -> None:
    client = FakeS3Client()
    store = S3StrategyPackageStore(settings(), client=client)  # type: ignore[arg-type]
    store.put_immutable("fleet/version.zip", b"first")

    store.delete("fleet/version.zip")
    store.delete("fleet/version.zip")

    assert client.objects == {}


def test_s3_store_reads_the_exact_immutable_bytes() -> None:
    client = FakeS3Client()
    store = S3StrategyPackageStore(settings(), client=client)  # type: ignore[arg-type]
    store.put_immutable("fleet/version.zip", b"first")

    assert store.get("fleet/version.zip") == b"first"
