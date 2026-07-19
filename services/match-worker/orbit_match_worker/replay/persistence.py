"""Persist completed replay streams and link them to their authoritative match."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC
from typing import Any, Protocol

from orbit_api.db.models import Match, ReplayArtifact
from orbit_api.domain.match_visibility import is_candidate_simulation
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from orbit_match_worker.replay.analysis import analyze_records


class ReplayWritableStore(Protocol):
    def put_immutable(self, key: str, content: bytes) -> object: ...


def persist_replay(
    match_public_id: str,
    content: bytes,
    *,
    frame_count: int,
    session_factory: sessionmaker[Session],
    store: ReplayWritableStore,
) -> str:
    """Upload one immutable artifact and idempotently attach its public row."""
    records = [json.loads(line) for line in gzip.decompress(content).splitlines()]
    header: dict[str, Any] = next((item for item in records if item.get("type") == "header"), {})
    result: dict[str, Any] = next(
        (item.get("result", {}) for item in records if item.get("type") == "result"), {}
    )
    analysis = analyze_records(records)
    checksum = hashlib.sha256(content).hexdigest()
    with session_factory() as session:
        match = session.scalar(select(Match).where(Match.public_id == match_public_id))
        if match is None:
            raise RuntimeError("cannot persist replay for a missing match")
        if match.replay_id is not None:
            current = session.get(ReplayArtifact, match.replay_id)
            if current is None:
                raise RuntimeError("match points to a missing replay artifact")
            return current.public_id
        created_at = match.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        date_partition = created_at.astimezone(UTC).strftime("%Y/%m/%d")

    object_key = f"replays/{date_partition}/{match_public_id}/{checksum}.jsonl.gz"

    store.put_immutable(object_key, content)

    with session_factory() as session:
        match = session.scalar(select(Match).where(Match.public_id == match_public_id))
        if match is None:
            raise RuntimeError("cannot attach replay to a missing match")
        if match.replay_id is not None:
            current = session.get(ReplayArtifact, match.replay_id)
            if current is None:
                raise RuntimeError("match points to a missing replay artifact")
            return current.public_id
        artifact = ReplayArtifact(
            object_key=object_key,
            schema_version=int(header.get("schemaVersion", 1)),
            checksum=checksum,
            metadata_payload={
                **header.get("match", {}),
                "participants": header.get("participants", []),
                "result": result,
            },
            analysis_payload={
                "events": [event.as_json() for event in analysis.events],
                "metrics": list(analysis.metrics),
                "facts": list(analysis.victory_facts),
            },
            size_bytes=len(content),
            frame_count=frame_count,
            is_public=not is_candidate_simulation(session, match.id),
        )
        session.add(artifact)
        session.flush()
        match.replay_id = artifact.id
        session.commit()
        return artifact.public_id
