"""Replay object access with optional S3 signed delivery."""

from __future__ import annotations

import hashlib
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from orbit_runtime.infrastructure import InfrastructureSettings


class ReplayStore(Protocol):
    def get(self, key: str) -> bytes: ...

    def signed_url(self, key: str, *, expires_seconds: int = 300) -> str | None: ...


class S3ReplayStore:
    def __init__(self, client: object, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_environment(cls) -> S3ReplayStore:
        settings = InfrastructureSettings.from_environment()
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
        return cls(client, settings.s3_bucket)

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)  # type: ignore[attr-defined]
        return response["Body"].read()  # type: ignore[no-any-return]

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)  # type: ignore[attr-defined]
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=self.bucket)  # type: ignore[attr-defined]

    def put_immutable(self, key: str, content: bytes) -> None:
        """Store a checksum-addressed replay without overwriting different bytes."""
        digest = hashlib.sha256(content).hexdigest()
        self.ensure_bucket()
        try:
            current = self.client.head_object(Bucket=self.bucket, Key=key)  # type: ignore[attr-defined]
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            if current.get("Metadata", {}).get("sha256") != digest or current.get(
                "ContentLength"
            ) != len(content):
                raise RuntimeError("immutable replay key already contains different bytes")
            return
        self.client.put_object(  # type: ignore[attr-defined]
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType="application/x-ndjson",
            ContentEncoding="gzip",
            Metadata={"sha256": digest},
        )

    def signed_url(self, key: str, *, expires_seconds: int = 300) -> str | None:
        return self.client.generate_presigned_url(  # type: ignore[attr-defined,no-any-return]
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
