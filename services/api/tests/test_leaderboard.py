import asyncio
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
    Rating,
    RatingEvent,
    ReplayArtifact,
    StrategyStatus,
    StrategyVersion,
    User,
)
from orbit_api.db.session import database_session
from orbit_api.main import app
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def public_client(tmp_path: Path) -> Iterator[tuple[httpx.AsyncClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path}/leaderboard.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[database_session] = test_session
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        yield client, factory
    finally:
        asyncio.run(client.aclose())
        app.dependency_overrides.clear()
        engine.dispose()


def get(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return asyncio.run(client.get(path))


def _version(fleet: Fleet, name: str) -> StrategyVersion:
    return StrategyVersion(
        fleet_id=fleet.id,
        content_hash=name.ljust(64, "0"),
        object_key=f"strategies/{name}.zip",
        manifest={"private": "must never be public"},
        notes=name,
        source="owner",
        submitted_by="owner",
        runtime_image="sandbox-v1",
        package_size_bytes=12,
        status=StrategyStatus.READY,
    )


def _seed(session: Session) -> tuple[Fleet, StrategyVersion, StrategyVersion]:
    users = [User(oidc_subject=f"public-{index}") for index in range(2)]
    session.add_all(users)
    session.flush()
    fleets = [
        Fleet(
            owner_user_id=user.id,
            name=f"Public Fleet {index}",
            commander_code=f"PUB-{index}",
            style_description="An original dark-metal orbital silhouette.",
        )
        for index, user in enumerate(users)
    ]
    session.add_all(fleets)
    session.flush()
    old_version = _version(fleets[0], "old")
    current_version = _version(fleets[0], "current")
    opponent_version = _version(fleets[1], "opponent")
    session.add_all([old_version, current_version, opponent_version])
    session.flush()
    fleets[0].current_strategy_version_id = current_version.id
    fleets[1].current_strategy_version_id = opponent_version.id
    session.add_all(
        [
            Rating(fleet_id=fleets[0].id, mu=32, sigma=4, display_score=2000),
            Rating(fleet_id=fleets[1].id, mu=28, sigma=5, display_score=1300),
        ]
    )
    replay = ReplayArtifact(
        object_key="replays/public.gz",
        schema_version=1,
        checksum="a" * 64,
        frame_count=21,
        size_bytes=100,
        is_public=True,
    )
    session.add(replay)
    session.flush()
    match = Match(
        ruleset_id="orbit-wars-2p-v1",
        seed=99,
        mode=MatchMode.RANKED,
        status=MatchStatus.FINISHED,
        result={"winnerSlot": 0, "reason": "elimination"},
        replay_id=replay.id,
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
                strategy_version_id=old_version.id,
            ),
            MatchParticipant(
                match_id=match.id,
                fleet_id=fleets[1].id,
                slot=1,
                controller_type=ControllerType.HUMAN,
            ),
            RatingEvent(
                match_id=match.id,
                changes=[
                    {"fleetPublicId": fleets[0].public_id, "delta": 42},
                    {"fleetPublicId": fleets[1].public_id, "delta": -42},
                ],
            ),
        ]
    )
    session.commit()
    return fleets[0], old_version, current_version


def test_filters_are_labels_over_one_rating_table(public_client) -> None:
    client, factory = public_client
    with factory() as session:
        own, _old, _current = _seed(session)
    all_entries = get(client, "/api/public/v1/leaderboard?period=all")
    agent_entries = get(client, "/api/public/v1/leaderboard?period=all&controller_type=agent")
    human_entries = get(client, "/api/public/v1/leaderboard?period=all&controller_type=human")
    with factory() as session:
        rating_count = session.scalar(select(func.count()).select_from(Rating))

    assert all_entries.status_code == 200
    assert [item["displayScore"] for item in all_entries.json()["entries"]] == [2000, 1300]
    assert all_entries.json()["entries"][0]["competitiveRank"] == {
        "tier": "master",
        "division": None,
        "points": 500,
    }
    assert all_entries.json()["entries"][1]["competitiveRank"] == {
        "tier": "diamond",
        "division": "II",
        "points": 0,
    }
    assert agent_entries.json()["entries"][0]["fleetPublicId"] == own.public_id
    assert human_entries.json()["entries"][0]["fleetPublicId"] != own.public_id
    assert rating_count == 2


def test_anonymous_profile_preserves_match_version_and_hides_private_storage(public_client) -> None:
    client, factory = public_client
    with factory() as session:
        own, old_version, current_version = _seed(session)
    response = get(client, f"/api/public/v1/fleet-profiles/{own.public_id}")
    body = response.json()

    assert response.status_code == 200
    assert body["currentStrategyVersionId"] == current_version.public_id
    assert body["rating"]["competitiveRank"] == {
        "tier": "master",
        "division": None,
        "points": 500,
    }
    assert body["matches"][0]["strategyVersionId"] == old_version.public_id
    assert body["matches"][0]["controllerType"] == "agent"
    assert body["matches"][0]["ratingChange"]["delta"] == 42
    assert body["representativeReplayPublicId"].startswith("replay_")
    assert "object_key" not in response.text
    assert "private" not in response.text


def test_public_match_history_contains_real_participants_and_replay(public_client) -> None:
    client, factory = public_client
    with factory() as session:
        own, old_version, _current = _seed(session)
    response = get(client, "/api/public/v1/matches?period=all&controller_type=agent")
    body = response.json()

    assert response.status_code == 200
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["replayPublicId"].startswith("replay_")
    assert match["participants"][0]["fleetPublicId"] == own.public_id
    assert match["participants"][0]["strategyVersionId"] == old_version.public_id
    assert match["participants"][0]["submittedBy"] == "owner"
    assert match["participants"][0]["ratingChange"]["delta"] == 42
    assert match["replayArtifact"] == {
        "schemaVersion": 1,
        "frameCount": 21,
        "sizeBytes": 100,
        "savedAt": match["replayArtifact"]["savedAt"],
    }
