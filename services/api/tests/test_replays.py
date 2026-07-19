import asyncio
import gzip
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from orbit_api.db.base import Base
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    ReplayArtifact,
    User,
)
from orbit_api.db.session import database_session
from orbit_api.main import app
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


class MemoryReplayStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def signed_url(self, key: str, *, expires_seconds: int = 300):
        del key, expires_seconds
        return None


@pytest.fixture
def replay_client(
    tmp_path: Path,
) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session], MemoryReplayStore]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/replays.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    store = MemoryReplayStore()
    app.dependency_overrides[database_session] = test_session
    app.state.replay_store = store
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        yield client, factory, store
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        del app.state.replay_store
        engine.dispose()


def get(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return asyncio.run(client.get(path))


def create_artifact(factory, store, *, public: bool = True) -> str:
    records = [
        {"type": "header", "schemaVersion": 1},
        {"type": "checkpoint", "frame": {"step": 0, "planets": [], "fleets": []}},
        {"type": "delta", "frame": {"step": 1, "planets": []}},
        {"type": "checkpoint", "frame": {"step": 20, "planets": [], "fleets": []}},
        {"type": "result", "result": {"finalStep": 20}},
    ]
    content = gzip.compress(("\n".join(json.dumps(record) for record in records) + "\n").encode())
    key = f"replays/{'public' if public else 'private'}.jsonl.gz"
    store.objects[key] = content
    with factory() as session:
        artifact = ReplayArtifact(
            object_key=key,
            schema_version=1,
            checksum=hashlib.sha256(content).hexdigest(),
            metadata_payload={"participants": [{"fleetName": "Ash Meridian"}]},
            analysis_payload={"events": [{"type": "match_finished", "step": 20}]},
            size_bytes=len(content),
            frame_count=21,
            is_public=public,
        )
        session.add(artifact)
        session.commit()
        session.refresh(artifact)
        return artifact.public_id


def test_anonymous_replay_metadata_stream_and_checkpoint_segment(replay_client) -> None:
    client, factory, store = replay_client
    public_id = create_artifact(factory, store)

    metadata = get(client, f"/api/public/v1/replays/{public_id}")
    artifact = get(client, f"/api/public/v1/replays/{public_id}/artifact")
    segment = get(client, f"/api/public/v1/replays/{public_id}/segments/0")
    compact = get(client, f"/api/public/v1/replays/{public_id}/compact")

    assert metadata.status_code == 200
    assert metadata.json()["frameCount"] == 21
    assert metadata.json()["analysis"]["events"][0]["type"] == "match_finished"
    assert metadata.json()["artifactUrl"].endswith(f"/{public_id}/artifact")
    assert artifact.status_code == 200
    assert b'"type": "header"' in artifact.content or b'"type":"header"' in artifact.content
    assert [record["type"] for record in segment.json()] == ["checkpoint", "delta"]
    assert compact.status_code == 200
    assert compact.json()["participants"][0]["fleetName"] == "Ash Meridian"
    assert compact.json()["events"][0]["type"] == "match_finished"
    assert compact.json()["deepLinks"]["artifact"].endswith(f"/{public_id}/artifact")


def test_private_replay_and_invalid_checkpoint_are_not_exposed(replay_client) -> None:
    client, factory, store = replay_client
    private_id = create_artifact(factory, store, public=False)
    public_id = create_artifact(factory, store, public=True)

    assert get(client, f"/api/public/v1/replays/{private_id}").status_code == 404
    invalid = get(client, f"/api/public/v1/replays/{public_id}/segments/7")
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "replay.invalid_checkpoint"


def test_legacy_public_candidate_replay_is_still_hidden(replay_client) -> None:
    client, factory, store = replay_client
    public_id = create_artifact(factory, store, public=True)
    with factory() as session:
        artifact = session.scalar(
            select(ReplayArtifact).where(ReplayArtifact.public_id == public_id)
        )
        assert artifact is not None
        users = [User(oidc_subject=f"candidate-{index}") for index in range(2)]
        session.add_all(users)
        session.flush()
        fleets = [
            Fleet(
                owner_user_id=user.id,
                name=f"Candidate Fleet {index}",
                commander_code=f"CAN-{index}",
                style_description="Private candidate replay test fleet.",
            )
            for index, user in enumerate(users)
        ]
        session.add_all(fleets)
        session.flush()
        match = Match(
            ruleset_id="orbit-wars-2p-v1",
            seed=77,
            mode=MatchMode.TRAINING,
            status=MatchStatus.FINISHED,
            replay_id=artifact.id,
        )
        session.add(match)
        session.flush()
        session.add_all(
            [
                MatchParticipant(
                    match_id=match.id,
                    fleet_id=fleets[0].id,
                    slot=0,
                    controller_type=ControllerType.AGENT,
                    candidate_content_hash="d" * 64,
                ),
                MatchParticipant(
                    match_id=match.id,
                    fleet_id=fleets[1].id,
                    slot=1,
                    controller_type=ControllerType.AGENT,
                ),
            ]
        )
        session.commit()

    for suffix in ["", "/compact", "/artifact", "/segments/0"]:
        response = get(client, f"/api/public/v1/replays/{public_id}{suffix}")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "replay.not_found"
