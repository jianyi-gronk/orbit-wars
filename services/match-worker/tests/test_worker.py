from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import pytest
from orbit_api.db.base import Base
from orbit_api.db.models import (
    ControllerType,
    Fleet,
    Match,
    MatchMode,
    MatchParticipant,
    MatchStatus,
    Rating,
    RatingEvent,
    ReplayArtifact,
    User,
)
from orbit_engine import PINNED_RULESET_ID
from orbit_match_worker.engine.adapter import EngineAdapter
from orbit_match_worker.runtime.agent_executor import observation_payload
from orbit_match_worker.worker import (
    MatchWorker,
    ParticipantSpec,
    QueuedMatch,
    _builtin_action,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


class SnapshotRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, **_options: Any) -> None:
        self.values[key] = value

    def xadd(self, *_args: Any, **_options: Any) -> None:
        return None


class MemoryReplayStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_immutable(self, key: str, content: bytes) -> None:
        self.objects.setdefault(key, content)


def test_worker_publishes_a_slot_scoped_live_snapshot() -> None:
    client = SnapshotRedis()
    worker = MatchWorker(cast(Any, client), turn_seconds=10)
    adapter = EngineAdapter(PINNED_RULESET_ID)
    initial = adapter.reset(seed=17, slots=(0, 1))

    worker._publish_snapshots("match-live", adapter, initial.step)

    first = json.loads(client.values["orbit:match:match-live:snapshot:0:v1"])
    second = json.loads(client.values["orbit:match:match-live:snapshot:1:v1"])
    assert first["type"] == "match.snapshot"
    assert first["payload"]["matchId"] == "match-live"
    assert first["payload"]["player"] == 0
    assert second["payload"]["player"] == 1
    assert first["payload"]["planets"]


def test_worker_runs_selected_kaggle_builtin() -> None:
    adapter = EngineAdapter(PINNED_RULESET_ID)
    initial = adapter.reset(seed=23, slots=(0, 1))
    observation = observation_payload("match-kaggle", initial, player=0)

    actions = _builtin_action("kaggle-structured-v11", observation)

    assert isinstance(actions, list)
    assert len(actions) <= 6
    assert all(len(action) == 3 for action in actions)
    assert all(0 <= float(action[1]) < math.tau for action in actions)


def test_worker_settles_finished_ranked_match_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/worker-rating.db")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("orbit_match_worker.worker.SessionLocal", session_factory)
    with Session(engine, expire_on_commit=False) as session:
        users = [User(oidc_subject=f"worker-rating-{index}") for index in range(2)]
        session.add_all(users)
        session.flush()
        fleets = [
            Fleet(
                owner_user_id=user.id,
                name=f"Worker Fleet {index}",
                commander_code=f"WF-{index}",
                style_description="A compact original test fleet.",
            )
            for index, user in enumerate(users)
        ]
        session.add_all(fleets)
        session.flush()
        match = Match(
            public_id="match-worker-rating",
            ruleset_id=PINNED_RULESET_ID,
            seed=29,
            mode=MatchMode.RANKED,
            status=MatchStatus.RUNNING,
            rating_multiplier=1,
        )
        session.add(match)
        session.flush()
        session.add_all(
            MatchParticipant(
                match_id=match.id,
                fleet_id=fleet.id,
                slot=slot,
                controller_type=ControllerType.AGENT,
            )
            for slot, fleet in enumerate(fleets)
        )
        session.commit()

    worker = MatchWorker(cast(Any, SnapshotRedis()))
    outcome = {"winnerSlot": 0, "reason": "elimination", "finalStep": 37}
    worker._finish("match-worker-rating", outcome)
    worker._finish("match-worker-rating", outcome)

    with Session(engine) as session:
        stored = session.scalar(select(Match).where(Match.public_id == "match-worker-rating"))
        assert stored is not None
        assert stored.status == MatchStatus.FINISHED
        assert session.scalar(select(func.count()).select_from(RatingEvent)) == 1
        ratings = list(session.scalars(select(Rating).order_by(Rating.display_score.desc())))
        assert len(ratings) == 2
        assert ratings[0].display_score > ratings[1].display_score


def test_worker_run_persists_public_replay_before_finishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path}/worker-replay.db")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("orbit_match_worker.worker.SessionLocal", session_factory)
    with session_factory() as session:
        session.add(
            Match(
                public_id="match-worker-replay",
                ruleset_id=PINNED_RULESET_ID,
                seed=43,
                mode=MatchMode.TRAINING,
                status=MatchStatus.PREPARING,
            )
        )
        session.commit()

    store = MemoryReplayStore()
    worker = MatchWorker(
        cast(Any, SnapshotRedis()),
        turn_seconds=0,
        replay_store=store,
        replay_directory=tmp_path,
    )
    worker._run(
        QueuedMatch(
            public_id="match-worker-replay",
            ruleset_id=PINNED_RULESET_ID,
            seed=43,
            map_id="orbit-standard-v1",
            mode=MatchMode.TRAINING,
            participants=(
                ParticipantSpec(
                    0,
                    ControllerType.AGENT,
                    "basic-v1",
                    "fleet-replay-a",
                    "Replay Alpha",
                    "strategy-replay-a",
                ),
                ParticipantSpec(
                    1,
                    ControllerType.AGENT,
                    "basic-v1",
                    "fleet-replay-b",
                    "Replay Beta",
                    "strategy-replay-b",
                ),
            ),
        )
    )

    with session_factory() as session:
        match = session.scalar(select(Match).where(Match.public_id == "match-worker-replay"))
        artifact = session.get(ReplayArtifact, match.replay_id) if match else None
        assert match is not None
        assert match.status == MatchStatus.FINISHED
        assert artifact is not None
        assert artifact.is_public is True
        assert artifact.frame_count > 1
        assert len(store.objects) == 1
