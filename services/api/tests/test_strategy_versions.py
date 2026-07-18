import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from orbit_api.db.base import Base
from orbit_api.db.models import Fleet, StrategyStatus, StrategyVersion
from orbit_api.domain.fleets import FleetNotFoundError, create_fleet
from orbit_api.domain.strategy_versions import (
    StrategyNotReadyError,
    StrategyPackageInvalidError,
    StrategyPublicationError,
    StrategyStatusTransitionError,
    inspect_package,
    list_strategy_versions,
    publish_strategy_version,
    set_current_strategy,
    transition_strategy_status,
)
from orbit_api.security.oidc import Principal
from orbit_api.storage.strategy_packages import (
    StoredPackage,
    StrategyPackageStoreError,
)
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


class MemoryPackageStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts = 0
        self.deleted: list[str] = []
        self.fail_put = False
        self.fail_delete = False

    def put_immutable(self, key: str, content: bytes) -> StoredPackage:
        self.puts += 1
        if self.fail_put:
            raise StrategyPackageStoreError("unavailable")
        existing = self.objects.get(key)
        if existing is not None:
            if existing != content:
                raise StrategyPackageStoreError("immutable key conflict")
            return StoredPackage(key=key, created=False)
        self.objects[key] = content
        return StoredPackage(key=key, created=True)

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise StrategyPackageStoreError("cleanup unavailable")
        self.deleted.append(key)
        self.objects.pop(key, None)


def package_bytes(*, marker: str = "alpha", manifest: object | None = None) -> bytes:
    manifest_value = (
        manifest if manifest is not None else {"schemaVersion": 1, "entrypoint": "main.py:agent"}
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest_value, separators=(",", ":")))
        archive.writestr("main.py", f"MARKER = {marker!r}\n")
    return output.getvalue()


def fleet_payload(name: str) -> dict[str, str]:
    return {
        "name": name,
        "commander_code": name.upper().replace(" ", "-")[:40],
        "declaration": "",
        "strategy_tendency": "balanced",
        "style_description": "An offset graphite ring with amber radiator vanes.",
    }


@pytest.fixture
def strategy_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/strategies.db")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def create_owned_fleet(session: Session, subject: str = "owner") -> tuple[Principal, Fleet]:
    principal = Principal(subject=subject, claims={"name": subject})
    fleet = create_fleet(
        session,
        principal,
        fleet_payload(f"Fleet {subject}"),
        provision_basic=False,
    )
    return principal, fleet


def publish(
    session: Session,
    store: MemoryPackageStore,
    principal: Principal,
    fleet: Fleet,
    content: bytes,
    *,
    notes: str = "First stable approach",
):
    return publish_strategy_version(
        session,
        store,
        principal,
        fleet.public_id,
        content,
        notes=notes,
        source="command-center",
        submitted_by="human:owner",
        runtime_image="orbit-agent-py311:phase1",
    )


def make_ready(session: Session, public_id: str) -> StrategyVersion:
    transition_strategy_status(session, public_id, StrategyStatus.VALIDATING)
    return transition_strategy_status(session, public_id, StrategyStatus.READY)


def test_publish_stores_content_addressed_package_and_deduplicates(
    strategy_session: Session,
) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    content = package_bytes()

    first = publish(strategy_session, store, principal, fleet, content)
    duplicate = publish(
        strategy_session,
        store,
        principal,
        fleet,
        content,
        notes="This metadata must not mutate the existing version",
    )

    digest = hashlib.sha256(content).hexdigest()
    assert first.deduplicated is False
    assert duplicate.deduplicated is True
    assert duplicate.version.id == first.version.id
    assert duplicate.version.notes == "First stable approach"
    assert first.version.content_hash == digest
    assert first.version.object_key == f"fleets/{fleet.public_id}/strategies/{digest}.zip"
    assert first.version.manifest == {"schemaVersion": 1, "entrypoint": "main.py:agent"}
    assert first.version.package_size_bytes == len(content)
    assert first.version.status is StrategyStatus.UPLOADED
    assert store.objects[first.version.object_key] == content
    assert store.puts == 1
    assert strategy_session.scalar(select(func.count(StrategyVersion.id))) == 1


def test_lifecycle_is_forward_only_and_current_pointer_requires_ready(
    strategy_session: Session,
) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    published = publish(strategy_session, store, principal, fleet, package_bytes())

    with pytest.raises(StrategyNotReadyError):
        set_current_strategy(
            strategy_session,
            principal,
            fleet.public_id,
            published.version.public_id,
        )
    with pytest.raises(StrategyStatusTransitionError):
        transition_strategy_status(
            strategy_session,
            published.version.public_id,
            StrategyStatus.READY,
        )

    ready = make_ready(strategy_session, published.version.public_id)
    set_current_strategy(
        strategy_session,
        principal,
        fleet.public_id,
        ready.public_id,
    )
    strategy_session.refresh(fleet)

    assert fleet.current_strategy_version_id == ready.id
    with pytest.raises(StrategyStatusTransitionError):
        transition_strategy_status(
            strategy_session,
            ready.public_id,
            StrategyStatus.REJECTED,
        )


def test_switching_current_only_moves_pointer_and_preserves_history(
    strategy_session: Session,
) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    first_content = package_bytes(marker="one")
    second_content = package_bytes(marker="two")
    first = publish(strategy_session, store, principal, fleet, first_content)
    second = publish(strategy_session, store, principal, fleet, second_content)
    make_ready(strategy_session, first.version.public_id)
    make_ready(strategy_session, second.version.public_id)

    set_current_strategy(strategy_session, principal, fleet.public_id, first.version.public_id)
    set_current_strategy(strategy_session, principal, fleet.public_id, second.version.public_id)
    versions = list_strategy_versions(strategy_session, principal, fleet.public_id)
    strategy_session.refresh(fleet)

    assert fleet.current_strategy_version_id == second.version.id
    assert {version.id for version in versions} == {first.version.id, second.version.id}
    assert all(version.status is StrategyStatus.READY for version in versions)
    assert store.objects[first.version.object_key] == first_content


def test_strategy_version_ownership_is_enforced(strategy_session: Session) -> None:
    owner, fleet = create_owned_fleet(strategy_session, "owner")
    other, _other_fleet = create_owned_fleet(strategy_session, "other")
    store = MemoryPackageStore()
    version = publish(strategy_session, store, owner, fleet, package_bytes()).version
    make_ready(strategy_session, version.public_id)

    with pytest.raises(FleetNotFoundError):
        list_strategy_versions(strategy_session, other, fleet.public_id)
    with pytest.raises(FleetNotFoundError):
        set_current_strategy(
            strategy_session,
            other,
            fleet.public_id,
            version.public_id,
        )


def test_storage_failure_creates_no_version(strategy_session: Session) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    store.fail_put = True

    with pytest.raises(StrategyPublicationError):
        publish(strategy_session, store, principal, fleet, package_bytes())

    assert strategy_session.scalar(select(func.count(StrategyVersion.id))) == 0


def test_database_failure_compensates_upload_and_retry_succeeds(
    strategy_session: Session,
) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    content = package_bytes()

    def fail_commit(_session: Session) -> None:
        raise OperationalError("INSERT strategy_versions", {}, RuntimeError("offline"))

    event.listen(strategy_session, "before_commit", fail_commit)
    with pytest.raises(StrategyPublicationError):
        publish(strategy_session, store, principal, fleet, content)
    event.remove(strategy_session, "before_commit", fail_commit)

    assert store.objects == {}
    assert len(store.deleted) == 1
    assert strategy_session.scalar(select(func.count(StrategyVersion.id))) == 0

    retried = publish(strategy_session, store, principal, fleet, content)
    assert retried.deduplicated is False
    assert strategy_session.scalar(select(func.count(StrategyVersion.id))) == 1


def test_cleanup_failure_leaves_retry_safe_content_key(strategy_session: Session) -> None:
    principal, fleet = create_owned_fleet(strategy_session)
    store = MemoryPackageStore()
    store.fail_delete = True
    content = package_bytes()

    def fail_commit(_session: Session) -> None:
        raise OperationalError("INSERT strategy_versions", {}, RuntimeError("offline"))

    event.listen(strategy_session, "before_commit", fail_commit)
    with pytest.raises(StrategyPublicationError):
        publish(strategy_session, store, principal, fleet, content)
    event.remove(strategy_session, "before_commit", fail_commit)

    assert len(store.objects) == 1
    retried = publish(strategy_session, store, principal, fleet, content)
    assert retried.deduplicated is False
    assert store.puts == 2
    assert len(store.objects) == 1


@pytest.mark.parametrize(
    "content",
    [
        b"not-a-zip",
        package_bytes(manifest=[]),
        package_bytes(manifest={"schemaVersion": 2, "entrypoint": "main.py:agent"}),
        package_bytes(manifest={"schemaVersion": 1, "entrypoint": "invalid"}),
    ],
)
def test_invalid_packages_are_rejected_before_storage(content: bytes) -> None:
    with pytest.raises(StrategyPackageInvalidError):
        inspect_package(content)
