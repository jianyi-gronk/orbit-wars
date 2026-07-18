"""Anonymous public replay metadata, streams, and checkpoint segments."""

from __future__ import annotations

import gzip
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.models import (
    Fleet,
    Match,
    MatchParticipant,
    RatingEvent,
    ReplayArtifact,
    StrategyVersion,
)
from orbit_api.db.session import database_session
from orbit_api.storage.replays import ReplayStore, S3ReplayStore

router = APIRouter(tags=["public replays"])
SessionDependency = Annotated[Session, Depends(database_session)]


def replay_store(request: Request) -> ReplayStore:
    store = getattr(request.app.state, "replay_store", None)
    if store is None:
        store = S3ReplayStore.from_environment()
        request.app.state.replay_store = store
    return store


def _public_replay(session: Session, public_id: str) -> tuple[ReplayArtifact, Match | None]:
    artifact = session.scalar(
        select(ReplayArtifact).where(
            ReplayArtifact.public_id == public_id,
            ReplayArtifact.is_public.is_(True),
        )
    )
    if artifact is None:
        raise HTTPException(404, detail={"code": "replay.not_found"})
    match = session.scalar(select(Match).where(Match.replay_id == artifact.id))
    return artifact, match


@router.get("/api/public/v1/replays/{public_id}")
def public_replay(
    public_id: str,
    request: Request,
    session: SessionDependency,
    store: Annotated[ReplayStore, Depends(replay_store)],
) -> dict[str, Any]:
    artifact, match = _public_replay(session, public_id)
    return {
        "publicId": artifact.public_id,
        "schemaVersion": artifact.schema_version,
        "checksum": artifact.checksum,
        "sizeBytes": artifact.size_bytes,
        "frameCount": artifact.frame_count,
        "matchPublicId": match.public_id if match else None,
        "metadata": artifact.metadata_payload,
        "analysis": artifact.analysis_payload,
        "artifactUrl": store.signed_url(artifact.object_key)
        or str(request.url_for("public_replay_artifact", public_id=public_id)),
        "segmentTemplate": str(
            request.url_for("public_replay_segment", public_id=public_id, checkpoint_step=0)
        ).replace("/0", "/{checkpointStep}"),
    }


@router.get("/api/public/v1/replays/{public_id}/compact")
def compact_public_replay(
    public_id: str,
    request: Request,
    session: SessionDependency,
) -> dict[str, Any]:
    artifact, match = _public_replay(session, public_id)
    participants: list[dict[str, Any]] = []
    rating_changes: list[dict[str, Any]] = []
    if match is not None:
        rows = session.execute(
            select(MatchParticipant, Fleet, StrategyVersion)
            .join(Fleet, Fleet.id == MatchParticipant.fleet_id)
            .outerjoin(StrategyVersion, StrategyVersion.id == MatchParticipant.strategy_version_id)
            .where(MatchParticipant.match_id == match.id)
            .order_by(MatchParticipant.slot)
        ).all()
        participants = [
            {
                "slot": participant.slot,
                "fleetPublicId": fleet.public_id,
                "fleetName": fleet.name,
                "commanderCode": fleet.commander_code,
                "controllerType": participant.controller_type,
                "strategyVersionId": version.public_id if version else None,
                "strategyContentHash": (
                    version.content_hash if version else participant.candidate_content_hash
                ),
                "strategySource": (
                    version.source
                    if version
                    else "simulation-candidate"
                    if participant.candidate_content_hash
                    else "human"
                ),
                "submittedBy": (
                    version.submitted_by if version else participant.candidate_submitted_by
                ),
            }
            for participant, fleet, version in rows
        ]
        rating_event = session.scalar(select(RatingEvent).where(RatingEvent.match_id == match.id))
        if rating_event is not None:
            rating_changes = rating_event.changes
    metadata = artifact.metadata_payload or {}
    analysis = artifact.analysis_payload or {}
    return {
        "schemaVersion": 1,
        "publicId": artifact.public_id,
        "matchPublicId": match.public_id if match else None,
        "mapId": match.map_id if match else metadata.get("mapId"),
        "mode": match.mode if match else metadata.get("mode"),
        "result": match.result if match else metadata.get("result"),
        "participants": participants or metadata.get("participants", []),
        "ratingChanges": rating_changes,
        "frameCount": artifact.frame_count,
        "events": analysis.get("events", []),
        "facts": analysis.get("facts", analysis.get("summary", [])),
        "deepLinks": {
            "metadata": str(request.url_for("public_replay", public_id=public_id)),
            "artifact": str(request.url_for("public_replay_artifact", public_id=public_id)),
            "segmentTemplate": str(
                request.url_for("public_replay_segment", public_id=public_id, checkpoint_step=0)
            ).replace("/0", "/{checkpointStep}"),
        },
    }


@router.get("/api/public/v1/replays/{public_id}/artifact", name="public_replay_artifact")
def public_replay_artifact(
    public_id: str,
    session: SessionDependency,
    store: Annotated[ReplayStore, Depends(replay_store)],
) -> Response:
    artifact, _match = _public_replay(session, public_id)
    content = store.get(artifact.object_key)
    if artifact.checksum and __import__("hashlib").sha256(content).hexdigest() != artifact.checksum:
        raise HTTPException(503, detail={"code": "replay.checksum_mismatch"})
    return Response(
        content, media_type="application/x-ndjson", headers={"Content-Encoding": "gzip"}
    )


@router.get(
    "/api/public/v1/replays/{public_id}/segments/{checkpoint_step}",
    name="public_replay_segment",
)
def public_replay_segment(
    public_id: str,
    checkpoint_step: int,
    session: SessionDependency,
    store: Annotated[ReplayStore, Depends(replay_store)],
) -> list[dict[str, Any]]:
    if checkpoint_step < 0 or checkpoint_step % 20 != 0:
        raise HTTPException(422, detail={"code": "replay.invalid_checkpoint"})
    artifact, _match = _public_replay(session, public_id)
    records = [
        json.loads(line) for line in gzip.decompress(store.get(artifact.object_key)).splitlines()
    ]
    segment: list[dict[str, Any]] = []
    collecting = False
    for record in records:
        if record.get("type") == "checkpoint":
            step = record.get("frame", {}).get("step")
            if collecting and step != checkpoint_step:
                break
            collecting = step == checkpoint_step
        if collecting:
            segment.append(record)
    if not segment:
        raise HTTPException(404, detail={"code": "replay.checkpoint_not_found"})
    return segment
