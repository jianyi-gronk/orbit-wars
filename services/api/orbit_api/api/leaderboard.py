"""Anonymous unified leaderboard and immutable-attribution fleet profiles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
    StrategyVersion,
)
from orbit_api.db.session import database_session
from orbit_api.domain.competition import (
    battle_intensity,
    competition_record,
    select_highlights,
)
from orbit_api.domain.ratings import (
    DEFAULT_MU,
    DEFAULT_SIGMA,
    competitive_rank_for,
    display_score,
    tier_for,
)

router = APIRouter(tags=["public competition"])
SessionDependency = Annotated[Session, Depends(database_session)]
Period = Literal["today", "week", "all"]
LeaderboardSort = Literal["score", "win_rate", "wins"]


def _cutoff(period: Period) -> datetime | None:
    now = datetime.now(UTC)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return None


def _participant_rows(
    session: Session,
    fleet: Fleet,
    period: Period,
    controller_type: ControllerType | None,
) -> list[tuple[MatchParticipant, Match]]:
    statement = (
        select(MatchParticipant, Match)
        .join(Match, Match.id == MatchParticipant.match_id)
        .where(
            MatchParticipant.fleet_id == fleet.id,
            Match.mode == MatchMode.RANKED,
            Match.status == MatchStatus.FINISHED,
        )
        .order_by(Match.created_at.desc())
    )
    cutoff = _cutoff(period)
    if cutoff is not None:
        statement = statement.where(Match.created_at >= cutoff)
    if controller_type is not None:
        statement = statement.where(MatchParticipant.controller_type == controller_type)
    return list(session.execute(statement).tuples())


def _record(rows: list[tuple[MatchParticipant, Match]]) -> dict[str, int | float]:
    return competition_record(
        (participant.slot, match.result if isinstance(match.result, dict) else None)
        for participant, match in rows
    )


def _control_tags(session: Session, fleet: Fleet) -> list[str]:
    values = session.scalars(
        select(MatchParticipant.controller_type)
        .where(MatchParticipant.fleet_id == fleet.id)
        .distinct()
    )
    return sorted(value.value for value in values)


@router.get("/api/public/v1/leaderboard")
def leaderboard(
    session: SessionDependency,
    period: Annotated[Period, Query()] = "all",
    controller_type: Annotated[ControllerType | None, Query()] = None,
    sort: Annotated[LeaderboardSort | None, Query()] = None,
) -> dict[str, Any]:
    resolved_sort: LeaderboardSort = sort or ("score" if period == "all" else "win_rate")
    rated = list(
        session.execute(
            select(Fleet, Rating)
            .join(Rating, Rating.fleet_id == Fleet.id)
            .order_by(Rating.display_score.desc(), Fleet.created_at)
        ).all()
    )
    entries: list[dict[str, Any]] = []
    for fleet, rating in rated:
        rows = _participant_rows(session, fleet, period, controller_type)
        if (period != "all" or controller_type is not None) and not rows:
            continue
        entries.append(
            {
                "fleetPublicId": fleet.public_id,
                "name": fleet.name,
                "commanderCode": fleet.commander_code,
                "tier": tier_for(rating.display_score),
                "competitiveRank": competitive_rank_for(rating.display_score).as_json(),
                "displayScore": rating.display_score,
                "mu": rating.mu,
                "sigma": rating.sigma,
                "controlTags": _control_tags(session, fleet),
                "record": _record(rows),
            }
        )
    if resolved_sort == "win_rate":
        entries.sort(
            key=lambda entry: (
                -entry["record"]["adjustedWinRate"],
                -entry["record"]["wins"],
                -entry["record"]["matches"],
                -entry["displayScore"],
                entry["name"].casefold(),
            )
        )
    elif resolved_sort == "wins":
        entries.sort(
            key=lambda entry: (
                -entry["record"]["wins"],
                -entry["record"]["adjustedWinRate"],
                -entry["record"]["matches"],
                -entry["displayScore"],
                entry["name"].casefold(),
            )
        )
    else:
        entries.sort(key=lambda entry: (-entry["displayScore"], entry["name"].casefold()))
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank
    return {
        "period": period,
        "controllerType": controller_type.value if controller_type else None,
        "sort": resolved_sort,
        "entries": entries,
    }


def _rating_change(session: Session, match: Match, fleet: Fleet) -> dict[str, Any] | None:
    event = session.scalar(select(RatingEvent).where(RatingEvent.match_id == match.id))
    if event is None:
        return None
    return next(
        (change for change in event.changes if change.get("fleetPublicId") == fleet.public_id),
        None,
    )


def _public_match(session: Session, match: Match, replay: ReplayArtifact) -> dict[str, Any]:
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
            "candidateContentHash": participant.candidate_content_hash,
            "strategySource": (
                version.source
                if version
                else "simulation-candidate"
                if participant.candidate_content_hash
                else "human"
            ),
            "submittedBy": version.submitted_by if version else participant.candidate_submitted_by,
            "ratingChange": _rating_change(session, match, fleet),
        }
        for participant, fleet, version in rows
    ]
    analysis = replay.analysis_payload if isinstance(replay.analysis_payload, dict) else None
    intensity = battle_intensity(
        analysis,
        replay.frame_count,
        [participant["ratingChange"] for participant in participants],
    )
    return {
        "publicId": match.public_id,
        "mode": match.mode,
        "status": match.status,
        "mapId": match.map_id,
        "result": match.result,
        "replayPublicId": replay.public_id,
        "replayArtifact": {
            "schemaVersion": replay.schema_version,
            "frameCount": replay.frame_count,
            "sizeBytes": replay.size_bytes,
            "savedAt": replay.created_at,
        },
        "createdAt": match.created_at,
        "finishedAt": match.finished_at,
        "featured": intensity["featured"],
        "intensity": intensity,
        "highlights": select_highlights(analysis),
        "participants": participants,
    }


@router.get("/api/public/v1/matches")
def public_matches(
    session: SessionDependency,
    period: Annotated[Period, Query()] = "all",
    controller_type: Annotated[ControllerType | None, Query()] = None,
    featured: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    statement = (
        select(Match, ReplayArtifact)
        .join(ReplayArtifact, ReplayArtifact.id == Match.replay_id)
        .where(Match.status == MatchStatus.FINISHED, ReplayArtifact.is_public.is_(True))
        .order_by(Match.created_at.desc())
        .limit(100)
    )
    cutoff = _cutoff(period)
    if cutoff is not None:
        statement = statement.where(Match.created_at >= cutoff)
    items: list[dict[str, Any]] = []
    for match, replay in session.execute(statement).all():
        item = _public_match(session, match, replay)
        if controller_type is not None and not any(
            participant["controllerType"] == controller_type for participant in item["participants"]
        ):
            continue
        if featured and not item["featured"]:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return {
        "period": period,
        "controllerType": controller_type.value if controller_type else None,
        "featured": featured,
        "matches": items,
    }


@router.get("/api/public/v1/fleet-profiles/{public_id}")
def fleet_profile(public_id: str, session: SessionDependency) -> dict[str, Any]:
    fleet = session.scalar(select(Fleet).where(Fleet.public_id == public_id))
    if fleet is None:
        raise HTTPException(404, detail={"code": "fleet.not_found"})
    rating = session.get(Rating, fleet.id)
    score = rating.display_score if rating else display_score(DEFAULT_MU, DEFAULT_SIGMA)
    versions = list(
        session.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.fleet_id == fleet.id)
            .order_by(StrategyVersion.created_at.desc())
        )
    )
    history = list(
        session.execute(
            select(MatchParticipant, Match, StrategyVersion, ReplayArtifact)
            .join(Match, Match.id == MatchParticipant.match_id)
            .outerjoin(StrategyVersion, StrategyVersion.id == MatchParticipant.strategy_version_id)
            .outerjoin(ReplayArtifact, ReplayArtifact.id == Match.replay_id)
            .where(MatchParticipant.fleet_id == fleet.id)
            .order_by(Match.created_at.desc())
            .limit(25)
        ).all()
    )
    rank = None
    if rating is not None:
        rank = 1 + int(
            session.scalar(
                select(func.count()).select_from(Rating).where(Rating.display_score > score)
            )
            or 0
        )
    matches = [
        {
            "publicId": match.public_id,
            "mode": match.mode,
            "status": match.status,
            "controllerType": participant.controller_type,
            "strategyVersionId": version.public_id if version else None,
            "result": match.result,
            "ratingChange": _rating_change(session, match, fleet),
            "replayPublicId": replay.public_id if replay and replay.is_public else None,
            "createdAt": match.created_at,
        }
        for participant, match, version, replay in history
    ]
    representative = next(
        (item["replayPublicId"] for item in matches if item["replayPublicId"]),
        None,
    )
    return {
        "publicId": fleet.public_id,
        "name": fleet.name,
        "commanderCode": fleet.commander_code,
        "declaration": fleet.declaration,
        "styleDescription": fleet.style_description,
        "strategyTendency": fleet.strategy_tendency,
        "rating": {
            "rank": rank,
            "tier": tier_for(score),
            "competitiveRank": competitive_rank_for(score).as_json(),
            "displayScore": score,
            "mu": rating.mu if rating else DEFAULT_MU,
            "sigma": rating.sigma if rating else DEFAULT_SIGMA,
        },
        "controlTags": _control_tags(session, fleet),
        "currentStrategyVersionId": next(
            (
                version.public_id
                for version in versions
                if version.id == fleet.current_strategy_version_id
            ),
            None,
        ),
        "versions": [
            {
                "publicId": version.public_id,
                "status": version.status,
                "notes": version.notes,
                "source": version.source,
                "createdAt": version.created_at,
            }
            for version in versions
        ],
        "representativeReplayPublicId": representative,
        "matches": matches,
    }
