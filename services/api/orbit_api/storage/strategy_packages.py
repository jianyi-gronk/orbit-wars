"""Immutable strategy-package storage backed by an S3-compatible service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.client import BaseClient  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from orbit_runtime.infrastructure import InfrastructureSettings


class StrategyPackageStoreError(RuntimeError):
    """Raised when immutable package storage cannot complete safely."""


@dataclass(frozen=True)
class StoredPackage:
    key: str
    created: bool


class StrategyPackageStore(Protocol):
    def put_immutable(self, key: str, content: bytes) -> StoredPackage: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class S3StrategyPackageStore:
    def __init__(
        self,
        settings: InfrastructureSettings,
        client: BaseClient | None = None,
    ) -> None:
        self.bucket = settings.s3_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 2}),
        )

    @classmethod
    def from_environment(cls) -> S3StrategyPackageStore:
        return cls(InfrastructureSettings.from_environment())

    def ensure_bucket(self) -> None:
        """Create the configured development bucket when it does not exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as error:
            if _error_code(error) not in {"404", "NoSuchBucket", "NotFound"}:
                raise StrategyPackageStoreError("object storage bucket is unavailable") from error
        try:
            self.client.create_bucket(Bucket=self.bucket)
        except ClientError as error:
            raise StrategyPackageStoreError("object storage bucket could not be created") from error

    def put_immutable(self, key: str, content: bytes) -> StoredPackage:
        digest = hashlib.sha256(content).hexdigest()
        existing = self._head(key)
        if existing is not None:
            self._assert_same_content(existing, digest, len(content))
            return StoredPackage(key=key, created=False)

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="application/zip",
                Metadata={"sha256": digest},
                IfNoneMatch="*",
            )
        except ClientError as error:
            if _error_code(error) in {
                "409",
                "412",
                "ConditionalRequestConflict",
                "PreconditionFailed",
            }:
                concurrent = self._head(key)
                if concurrent is not None:
                    self._assert_same_content(concurrent, digest, len(content))
                    return StoredPackage(key=key, created=False)
            raise StrategyPackageStoreError("strategy package upload failed") from error
        return StoredPackage(key=key, created=True)

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            raise StrategyPackageStoreError("strategy package cleanup failed") from error

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return bytes(response["Body"].read())
        except ClientError as error:
            raise StrategyPackageStoreError("strategy package download failed") from error

    def _head(self, key: str) -> dict[str, Any] | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return cast(dict[str, Any], response)
        except ClientError as error:
            if _error_code(error) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StrategyPackageStoreError("strategy package lookup failed") from error

    @staticmethod
    def _assert_same_content(metadata: dict[str, Any], digest: str, size: int) -> None:
        stored_digest = metadata.get("Metadata", {}).get("sha256")
        stored_size = metadata.get("ContentLength")
        if stored_digest != digest or stored_size != size:
            raise StrategyPackageStoreError(
                "immutable strategy package key already has other content"
            )


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
