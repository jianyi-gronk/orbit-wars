from __future__ import annotations

import gzip
import json
from pathlib import Path

from orbit_api.db.base import Base
from orbit_api.db.models import Match, MatchMode, MatchStatus, ReplayArtifact
from orbit_engine import PINNED_RULESET_ID, OrbitEngine
from orbit_match_worker.replay import ReplayStreamWriter, persist_replay
from orbit_match_worker.replay.backfill import build_replay_content
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


class MemoryWritableStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_immutable(self, key: str, content: bytes) -> None:
        current = self.objects.get(key)
        if current is not None and current != content:
            raise RuntimeError("immutable key collision")
        self.objects[key] = content


def test_persist_replay_uploads_public_artifact_and_links_match_idempotently(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/persist-replay.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            Match(
                public_id="match-persist-replay",
                ruleset_id=PINNED_RULESET_ID,
                seed=41,
                mode=MatchMode.RANKED,
                status=MatchStatus.RUNNING,
            )
        )
        session.commit()

    writer = ReplayStreamWriter(
        tmp_path / "persist.jsonl.gz",
        match={"publicId": "match-persist-replay", "rulesetId": PINNED_RULESET_ID},
        participants=[],
    )
    writer.append(OrbitEngine().reset(seed=41), ([], []))
    info = writer.finalize({"winnerSlot": None, "reason": "step_limit", "finalStep": 0})
    store = MemoryWritableStore()

    first = persist_replay(
        "match-persist-replay",
        info.path.read_bytes(),
        frame_count=info.frame_count,
        session_factory=factory,
        store=store,
    )
    second = persist_replay(
        "match-persist-replay",
        info.path.read_bytes(),
        frame_count=info.frame_count,
        session_factory=factory,
        store=store,
    )

    with Session(engine) as session:
        match = session.scalar(select(Match).where(Match.public_id == "match-persist-replay"))
        artifact = session.get(ReplayArtifact, match.replay_id) if match else None
        assert first == second
        assert artifact is not None
        assert artifact.is_public is True
        assert artifact.frame_count == 1
        assert session.scalar(select(func.count()).select_from(ReplayArtifact)) == 1
        assert list(store.objects) == [artifact.object_key]
        assert artifact.object_key.startswith("replays/")
        assert f"/match-persist-replay/{artifact.checksum}.jsonl.gz" in artifact.object_key
        assert len(artifact.object_key.split("/")) == 6


def test_backfill_builds_checkpointed_gzip_from_authoritative_frame_events() -> None:
    frames = [
        {
            "step": step,
            "planets": [
                {
                    "id": 0,
                    "owner": 0,
                    "x": 1.0,
                    "y": 2.0,
                    "radius": 1.0,
                    "ships": 20 + step,
                    "production": 2,
                }
            ],
            "fleets": [],
        }
        for step in range(1, 22)
    ]
    content, frame_count = build_replay_content(
        match={"publicId": "match-backfill", "rulesetId": PINNED_RULESET_ID},
        participants=[],
        frames=frames,
        result={"winnerSlot": 0, "reason": "elimination", "finalStep": 21, "rewards": [1, -1]},
    )
    records = [json.loads(line) for line in gzip.decompress(content).splitlines()]
    checkpoints = [item["frame"]["step"] for item in records if item.get("type") == "checkpoint"]

    assert frame_count == 22
    assert checkpoints == [0, 20]
    assert records[1]["frame"]["planets"][0] == [0, 0, 1.0, 2.0, 1.0, 21, 2]
    assert records[-1]["result"]["winnerSlot"] == 0
