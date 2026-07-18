"""Immutable strategy version publication and lifecycle rules."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from orbit_api.db.models import StrategyStatus, StrategyVersion
from orbit_api.domain.fleets import get_owned_fleet
from orbit_api.security.oidc import Principal
from orbit_api.security.public_ids import new_public_id
from orbit_api.storage.strategy_packages import (
    StoredPackage,
    StrategyPackageStore,
    StrategyPackageStoreError,
)

MAX_PACKAGE_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
MAX_NOTES_LENGTH = 1000
MAX_SOURCE_LENGTH = 255
MAX_SUBMITTED_BY_LENGTH = 120
MAX_RUNTIME_IMAGE_LENGTH = 255
_ENTRYPOINT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_/]*\.py:[A-Za-z_][A-Za-z0-9_]*$")


class StrategyVersionError(Exception):
    code = "strategy.error"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class StrategyPackageInvalidError(StrategyVersionError):
    code = "strategy.invalid_package"


class StrategyVersionNotFoundError(StrategyVersionError):
    code = "strategy.not_found"


class StrategyStatusTransitionError(StrategyVersionError):
    code = "strategy.invalid_status_transition"


class StrategyNotReadyError(StrategyVersionError):
    code = "strategy.not_ready"


class StrategyPublicationError(StrategyVersionError):
    code = "strategy.publication_failed"


@dataclass(frozen=True)
class StrategyPublication:
    version: StrategyVersion
    deduplicated: bool


_ALLOWED_TRANSITIONS = {
    StrategyStatus.UPLOADED: {StrategyStatus.VALIDATING},
    StrategyStatus.VALIDATING: {StrategyStatus.READY, StrategyStatus.REJECTED},
    StrategyStatus.READY: set(),
    StrategyStatus.REJECTED: set(),
}


def publish_strategy_version(
    session: Session,
    store: StrategyPackageStore,
    principal: Principal,
    fleet_public_id: str,
    package: bytes,
    *,
    notes: str,
    source: str,
    submitted_by: str,
    runtime_image: str,
) -> StrategyPublication:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    manifest = inspect_package(package)
    normalized_notes = _metadata_text("notes", notes, MAX_NOTES_LENGTH, allow_empty=True)
    normalized_source = _metadata_text("source", source, MAX_SOURCE_LENGTH)
    normalized_submitter = _metadata_text("submitted_by", submitted_by, MAX_SUBMITTED_BY_LENGTH)
    normalized_runtime = _metadata_text("runtime_image", runtime_image, MAX_RUNTIME_IMAGE_LENGTH)
    content_hash = hashlib.sha256(package).hexdigest()

    existing = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.fleet_id == fleet.id,
            StrategyVersion.content_hash == content_hash,
        )
    )
    if existing is not None:
        return StrategyPublication(version=existing, deduplicated=True)

    object_key = f"fleets/{fleet.public_id}/strategies/{content_hash}.zip"
    try:
        stored = store.put_immutable(object_key, package)
    except StrategyPackageStoreError as error:
        session.rollback()
        raise StrategyPublicationError("strategy package could not be stored") from error

    version = StrategyVersion(
        public_id=new_public_id("strategy"),
        fleet_id=fleet.id,
        content_hash=content_hash,
        object_key=object_key,
        manifest=manifest,
        notes=normalized_notes,
        source=normalized_source,
        submitted_by=normalized_submitter,
        runtime_image=normalized_runtime,
        package_size_bytes=len(package),
        status=StrategyStatus.UPLOADED,
    )
    session.add(version)
    try:
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        _compensate_upload(store, stored)
        raise StrategyPublicationError("strategy version metadata could not be saved") from error
    session.refresh(version)
    return StrategyPublication(version=version, deduplicated=False)


def inspect_package(package: bytes) -> dict[str, Any]:
    if not package or len(package) > MAX_PACKAGE_BYTES:
        raise StrategyPackageInvalidError(
            f"package must contain 1-{MAX_PACKAGE_BYTES} bytes",
            field="package",
        )
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            matching_names = [name for name in archive.namelist() if name == "manifest.json"]
            if len(matching_names) != 1:
                raise StrategyPackageInvalidError(
                    "package must contain one root manifest.json",
                    field="package",
                )
            info = archive.getinfo("manifest.json")
            if info.file_size > MAX_MANIFEST_BYTES:
                raise StrategyPackageInvalidError("manifest.json is too large", field="manifest")
            manifest_value = json.loads(archive.read(info).decode("utf-8"))
    except StrategyPackageInvalidError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile, OSError) as error:
        raise StrategyPackageInvalidError(
            "package must be a readable ZIP with a UTF-8 JSON manifest",
            field="package",
        ) from error

    if not isinstance(manifest_value, dict):
        raise StrategyPackageInvalidError("manifest must be a JSON object", field="manifest")
    if manifest_value.get("schemaVersion") != 1:
        raise StrategyPackageInvalidError("manifest schemaVersion must be 1", field="manifest")
    entrypoint = manifest_value.get("entrypoint")
    if not isinstance(entrypoint, str) or not _ENTRYPOINT_PATTERN.fullmatch(entrypoint):
        raise StrategyPackageInvalidError(
            "manifest entrypoint must use path.py:function syntax",
            field="manifest",
        )
    return manifest_value


def list_strategy_versions(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
) -> list[StrategyVersion]:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    return list(
        session.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.fleet_id == fleet.id)
            .order_by(StrategyVersion.created_at.desc())
        )
    )


def transition_strategy_status(
    session: Session,
    version_id: str,
    target: StrategyStatus,
) -> StrategyVersion:
    version = session.scalar(select(StrategyVersion).where(StrategyVersion.public_id == version_id))
    if version is None:
        raise StrategyVersionNotFoundError("strategy version was not found")
    current = StrategyStatus(version.status)
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise StrategyStatusTransitionError(f"cannot move strategy from {current} to {target}")
    version.status = target
    session.commit()
    session.refresh(version)
    return version


def set_current_strategy(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
    strategy_public_id: str,
) -> StrategyVersion:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    version = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.public_id == strategy_public_id,
            StrategyVersion.fleet_id == fleet.id,
        )
    )
    if version is None:
        raise StrategyVersionNotFoundError("strategy version was not found")
    if StrategyStatus(version.status) is not StrategyStatus.READY:
        raise StrategyNotReadyError("only a ready strategy can become current")
    fleet.current_strategy_version_id = version.id
    session.commit()
    session.refresh(version)
    return version


def _metadata_text(field: str, value: Any, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise StrategyPackageInvalidError("must be text", field=field)
    normalized = " ".join(value.split())
    minimum = 0 if allow_empty else 1
    if not minimum <= len(normalized) <= maximum:
        raise StrategyPackageInvalidError(
            f"must contain {minimum}-{maximum} characters",
            field=field,
        )
    return normalized


def _compensate_upload(store: StrategyPackageStore, stored: StoredPackage) -> None:
    if not stored.created:
        return
    try:
        store.delete(stored.key)
    except StrategyPackageStoreError:
        # The content-addressed key is safe to leave orphaned: the next retry writes
        # the same bytes to the same key and can then commit the missing DB record.
        return
