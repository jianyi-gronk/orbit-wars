"""Backfill public replay artifacts for finished matches from Redis Streams."""

from __future__ import annotations

import json

from orbit_api.db.models import (
    Fleet,
    Match,
    MatchParticipant,
    MatchStatus,
    StrategyVersion,
)
from orbit_api.db.session import SessionLocal
from orbit_api.storage.replays import S3ReplayStore
from orbit_match_worker.replay.backfill import build_replay_content
from orbit_match_worker.replay.persistence import persist_replay
from orbit_runtime.infrastructure import InfrastructureSettings
from redis import Redis
from sqlalchemy import select


def main() -> None:
    settings = InfrastructureSettings.from_environment()
    client = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=60)
    store = S3ReplayStore.from_environment()
    with SessionLocal() as session:
        matches = list(
            session.scalars(
                select(Match)
                .where(Match.status == MatchStatus.FINISHED, Match.replay_id.is_(None))
                .order_by(Match.created_at)
            )
        )
        contexts = [
            {
                "publicId": match.public_id,
                "rulesetId": match.ruleset_id,
                "seed": match.seed,
                "mapId": match.map_id,
                "mode": match.mode.value,
                "result": match.result or {},
                "participants": _participants(session, match),
            }
            for match in matches
        ]

    created: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for context in contexts:
        public_id = str(context["publicId"])
        frames = _frames(client, public_id)
        if not frames:
            skipped.append({"matchPublicId": public_id, "reason": "redis_frames_missing"})
            continue
        content, frame_count = build_replay_content(
            match={key: context[key] for key in ("publicId", "rulesetId", "seed", "mapId", "mode")},
            participants=context["participants"],  # type: ignore[arg-type]
            frames=frames,
            result=context["result"],  # type: ignore[arg-type]
        )
        replay_id = persist_replay(
            public_id,
            content,
            frame_count=frame_count,
            session_factory=SessionLocal,
            store=store,
        )
        created.append(
            {"matchPublicId": public_id, "replayPublicId": replay_id, "frameCount": frame_count}
        )
    print(json.dumps({"created": created, "skipped": skipped}, indent=2))


def _participants(session, match: Match) -> list[dict[str, object]]:
    rows = session.execute(
        select(MatchParticipant, Fleet, StrategyVersion)
        .join(Fleet, Fleet.id == MatchParticipant.fleet_id)
        .outerjoin(StrategyVersion, StrategyVersion.id == MatchParticipant.strategy_version_id)
        .where(MatchParticipant.match_id == match.id)
        .order_by(MatchParticipant.slot)
    ).all()
    return [
        {
            "fleetPublicId": fleet.public_id,
            "fleetName": fleet.name,
            "slot": participant.slot,
            "controllerType": participant.controller_type.value,
            "strategyVersionId": version.public_id if version else None,
        }
        for participant, fleet, version in rows
    ]


def _frames(client: Redis, match_public_id: str) -> list[dict[str, object]]:
    stream = f"orbit:match:{match_public_id}:events:v1"
    rows: list[tuple[str, dict[str, str]]] = []
    cursor = "-"
    while True:
        batch = client.xrange(stream, min=cursor, max="+", count=250)
        if cursor != "-" and batch:
            batch = batch[1:]
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0]
        if len(batch) < 249:
            break
    events = [json.loads(fields["payload"]) for _row_id, fields in rows]
    return [event["payload"] for event in events if event.get("type") == "match.frame"]


if __name__ == "__main__":
    main()
