import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from orbit_api.builtin_strategies.registry import (
    BASIC,
    EXPERT_V69,
    KAGGLE_STRUCTURED_V11,
    TRAINING,
)
from orbit_api.db.base import Base
from orbit_api.db.models import Fleet, StrategyStatus, StrategyVersion
from orbit_api.domain.fleets import create_fleet
from orbit_api.domain.strategy_validation import (
    LocalSandboxSession,
    StrategyValidationError,
    safe_extract,
    validate_package,
    validate_strategy_version,
)
from orbit_api.domain.strategy_versions import publish_strategy_version
from orbit_api.security.oidc import Principal
from orbit_api.storage.strategy_packages import StoredPackage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_immutable(self, key: str, content: bytes) -> StoredPackage:
        created = key not in self.objects
        self.objects.setdefault(key, content)
        return StoredPackage(key, created)

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture
def validation_context(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/validation.db")
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    principal = Principal(subject="validator-owner", claims={})
    fleet = create_fleet(
        session,
        principal,
        {
            "name": "Validation Fleet",
            "commander_code": "VALIDATE",
            "declaration": "",
            "strategy_tendency": "balanced",
            "style_description": "A dark radial hull with a narrow copper signal vane.",
        },
        provision_basic=False,
    )
    store = MemoryStore()
    try:
        yield session, principal, fleet, store
    finally:
        session.close()
        engine.dispose()


def publish_package(
    session: Session,
    principal: Principal,
    fleet: Fleet,
    store: MemoryStore,
    package: bytes,
) -> StrategyVersion:
    return publish_strategy_version(
        session,
        store,
        principal,
        fleet.public_id,
        package,
        notes="validation candidate",
        source="test",
        submitted_by="human:test",
        runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
    ).version


def custom_package(source: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"schemaVersion": 1, "entrypoint": "main.py:agent"}),
        )
        archive.writestr("main.py", source)
    return output.getvalue()


def unsafe_package(name: str, content: bytes, *, mode: int | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        info = zipfile.ZipInfo(name)
        if mode is not None:
            info.external_attr = mode << 16
        archive.writestr(info, content)
    return output.getvalue()


def test_builtin_packages_are_deterministic_and_auditable() -> None:
    assert BASIC.package_bytes() == BASIC.package_bytes()
    assert TRAINING.package_bytes() == TRAINING.package_bytes()
    assert EXPERT_V69.package_bytes() == EXPERT_V69.package_bytes()
    assert KAGGLE_STRUCTURED_V11.package_bytes() == KAGGLE_STRUCTURED_V11.package_bytes()
    assert BASIC.content_hash == hashlib.sha256(BASIC.package_bytes()).hexdigest()
    assert (
        KAGGLE_STRUCTURED_V11.content_hash
        == hashlib.sha256(KAGGLE_STRUCTURED_V11.package_bytes()).hexdigest()
    )
    assert len(EXPERT_V69.source_files) >= 17
    with zipfile.ZipFile(io.BytesIO(EXPERT_V69.package_bytes())) as archive:
        assert "entrypoint.py" in archive.namelist()
        assert "orbit_lite/planner_core.py" in archive.namelist()
    with zipfile.ZipFile(io.BytesIO(KAGGLE_STRUCTURED_V11.package_bytes())) as archive:
        assert {"entrypoint.py", "main.py"}.issubset(archive.namelist())


@pytest.mark.parametrize(
    ("package", "code"),
    [
        (unsafe_package("../escape.py", b"bad"), "package.unsafe_path"),
        (unsafe_package("folder\\escape.py", b"bad"), "package.unsafe_path"),
        (
            unsafe_package("linked.py", b"target", mode=stat.S_IFLNK | 0o777),
            "package.symlink",
        ),
    ],
)
def test_safe_extract_rejects_paths_and_links(
    tmp_path: Path,
    package: bytes,
    code: str,
) -> None:
    with pytest.raises(StrategyValidationError) as raised:
        safe_extract(package, tmp_path)
    assert raised.value.code == code


@pytest.mark.parametrize("builtin", [BASIC, TRAINING, KAGGLE_STRUCTURED_V11])
def test_stdlib_builtins_pass_contract_and_fixed_match(builtin) -> None:
    report = validate_package(
        builtin.package_bytes(),
        runtime_image=builtin.runtime_image,
        sandbox_factory=LocalSandboxSession,
    )

    assert report.result == "ready"
    assert report.fixed_steps == 24
    assert report.checks == (
        "safe_extract",
        "import",
        "contract",
        "resources",
        "fixed_match",
    )


def test_validation_writes_ready_report(validation_context) -> None:
    session, principal, fleet, store = validation_context
    version = publish_package(session, principal, fleet, store, BASIC.package_bytes())

    result = validate_strategy_version(
        session,
        store,
        version.public_id,
        sandbox_factory=LocalSandboxSession,
    )

    assert result.status is StrategyStatus.READY
    assert result.validation_report["result"] == "ready"
    assert result.validation_report["fixedSteps"] == 24
    assert result.validated_at is not None


def test_bad_agent_is_rejected_with_safe_reason(validation_context) -> None:
    session, principal, fleet, store = validation_context
    package = custom_package(
        "def agent(obs):\n    raise RuntimeError('database-password-secret')\n"
    )
    version = publish_package(session, principal, fleet, store, package)

    result = validate_strategy_version(
        session,
        store,
        version.public_id,
        sandbox_factory=LocalSandboxSession,
    )

    assert result.status is StrategyStatus.REJECTED
    assert result.validation_report == {
        "result": "rejected",
        "code": "agent.exception",
        "message": "The strategy raised an error during its fixed validation match.",
    }
    assert "database-password-secret" not in json.dumps(result.validation_report)


def test_checksum_mismatch_rejects_without_running_agent(validation_context) -> None:
    session, principal, fleet, store = validation_context
    version = publish_package(session, principal, fleet, store, BASIC.package_bytes())
    store.objects[version.object_key] = TRAINING.package_bytes()

    result = validate_strategy_version(
        session,
        store,
        version.public_id,
        sandbox_factory=LocalSandboxSession,
    )

    assert result.status is StrategyStatus.REJECTED
    assert result.validation_report["code"] == "package.checksum_mismatch"


def test_new_fleet_has_immediately_ready_basic_version(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/starter.db")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        fleet = create_fleet(
            session,
            Principal(subject="new-captain", claims={}),
            {
                "name": "Starter Fleet",
                "commander_code": "STARTER",
                "declaration": "",
                "strategy_tendency": "balanced",
                "style_description": "A pale crescent frame with a centered amber drive ring.",
            },
        )
        starter = session.scalar(
            select(StrategyVersion).where(StrategyVersion.id == fleet.current_strategy_version_id)
        )

    assert starter is not None
    assert starter.status is StrategyStatus.READY
    assert starter.object_key == "builtin://basic-v1"
    assert starter.content_hash == BASIC.content_hash


def test_new_fleet_can_select_kaggle_starter(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/kaggle-starter.db")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        fleet = create_fleet(
            session,
            Principal(subject="kaggle-captain", claims={}),
            {
                "name": "Kaggle Fleet",
                "commander_code": "KAGGLE",
                "declaration": "",
                "strategy_tendency": "balanced",
                "strategy_template": "kaggle-structured-v11",
                "style_description": "A compact graphite ring with two amber guidance vanes.",
            },
        )
        starter = session.scalar(
            select(StrategyVersion).where(StrategyVersion.id == fleet.current_strategy_version_id)
        )

    assert starter is not None
    assert starter.status is StrategyStatus.READY
    assert starter.object_key == "builtin://kaggle-structured-v11"
    assert starter.content_hash == KAGGLE_STRUCTURED_V11.content_hash
    assert starter.source == "kaggle"
    assert starter.submitted_by == "pilkwang via Kaggle"


@pytest.mark.skipif(
    os.environ.get("ORBIT_RUN_DOCKER_TESTS") != "1",
    reason="set ORBIT_RUN_DOCKER_TESTS=1 after building both sandbox images",
)
@pytest.mark.parametrize("builtin", [BASIC, EXPERT_V69])
def test_builtins_pass_real_sandbox_fixed_match(builtin) -> None:
    report = validate_package(
        builtin.package_bytes(),
        runtime_image=builtin.runtime_image,
    )
    assert report.result == "ready"
    assert report.fixed_steps == 24
