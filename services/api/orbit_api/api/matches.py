"""Match creation, queueing, and slot-bound ticket APIs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.models import Fleet, MatchParticipant, StrategyVersion, User
from orbit_api.db.session import database_session
from orbit_api.domain.match_tickets import MatchTicketService
from orbit_api.domain.matches import (
    MatchCreationConflict,
    MatchCreationError,
    MatchCreationRequest,
    create_match,
    match_for_fleet,
)
from orbit_api.domain.matchmaking import Matchmaker, MatchmakingError
from orbit_api.infrastructure.match_queue import MatchQueue, RedisMatchQueue
from orbit_api.security.oidc import Principal, current_principal


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class MatchCreateBody(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")
    fleet_id: str
    opponent_fleet_id: str
    mode: Literal["training", "ranked"]
    controller_type: Literal["human", "agent"]
    opponent_controller_type: Literal["human", "agent"]
    map_id: str = "orbit-standard-v1"
    idempotency_key: str = Field(min_length=1, max_length=128)


router = APIRouter(tags=["matches"])
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def match_queue(request: Request) -> MatchQueue:
    queue = getattr(request.app.state, "match_queue", None)
    if queue is None:
        queue = RedisMatchQueue.from_environment()
        request.app.state.match_queue = queue
    return queue


def ticket_service(request: Request) -> MatchTicketService:
    service = getattr(request.app.state, "match_ticket_service", None)
    if service is None:
        service = MatchTicketService()
        request.app.state.match_ticket_service = service
    return service


def _error(error: MatchCreationError) -> HTTPException:
    if error.code == "match.not_found":
        status_code = 404
    elif isinstance(error, MatchCreationConflict):
        status_code = 409
    else:
        status_code = 422
    return HTTPException(status_code, detail={"code": error.code, "message": str(error)})


def _response(session: Session, match: object) -> dict[str, object]:
    from orbit_api.db.models import Match

    assert isinstance(match, Match)
    participants = session.execute(
        select(MatchParticipant, Fleet, StrategyVersion)
        .join(Fleet, Fleet.id == MatchParticipant.fleet_id)
        .outerjoin(StrategyVersion, StrategyVersion.id == MatchParticipant.strategy_version_id)
        .where(MatchParticipant.match_id == match.id)
        .order_by(MatchParticipant.slot)
    ).all()
    return {
        "publicId": match.public_id,
        "mode": match.mode,
        "status": match.status,
        "mapId": match.map_id,
        "matchmakingReason": match.matchmaking_reason,
        "participants": [
            {
                "slot": participant.slot,
                "fleetPublicId": fleet.public_id,
                "controllerType": participant.controller_type,
                "strategyVersionId": version.public_id if version else None,
            }
            for participant, fleet, version in participants
        ],
    }


@router.get("/api/v1/matchmaking/offers")
def matchmaking_offer(
    fleet_id: str,
    controller_type: Literal["human", "agent"],
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, object]:
    fleet = session.scalar(
        select(Fleet)
        .join(User, User.id == Fleet.owner_user_id)
        .where(Fleet.public_id == fleet_id, User.oidc_subject == principal.subject)
    )
    if fleet is None:
        raise HTTPException(404, detail={"code": "fleet.not_found"})
    try:
        offer = Matchmaker().find(session, fleet, controller_type)
    except MatchmakingError as error:
        raise HTTPException(404, detail={"code": error.code, "message": str(error)}) from error
    return {
        "opponentFleetId": offer.opponent.public_id,
        "opponentName": offer.opponent.name,
        "reason": offer.reason,
        "ratingDifference": offer.rating_difference,
        "recentRepeats": offer.recent_repeats,
        "ratingMultiplier": offer.rating_multiplier,
        "controllerType": controller_type,
    }


@router.post("/api/v1/matches", status_code=201)
def create_match_route(
    payload: MatchCreateBody,
    request: Request,
    session: SessionDependency,
    principal: PrincipalDependency,
    queue: Annotated[MatchQueue, Depends(match_queue)],
    tickets: Annotated[MatchTicketService, Depends(ticket_service)],
) -> dict[str, object]:
    try:
        values = payload.model_dump(exclude={"idempotency_key"})
        match, slot, replayed = create_match(
            session,
            queue,
            principal,
            MatchCreationRequest(**values),
            idempotency_key=payload.idempotency_key,
        )
    except MatchCreationError as error:
        raise _error(error) from error
    issued = tickets.issue(
        match_id=match.public_id,
        fleet_id=payload.fleet_id,
        slot=slot,
        subject=principal.subject,
    )
    return {
        **_response(session, match),
        "ticket": issued.token,
        "ticketExpiresAt": issued.expires_at,
        "playerSlot": slot,
        "idempotentReplay": replayed,
    }


@router.get("/api/v1/matches/{match_id}")
def read_match_route(
    match_id: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, object]:
    fleet = session.scalar(
        select(Fleet)
        .join(User, User.id == Fleet.owner_user_id)
        .where(User.oidc_subject == principal.subject)
    )
    if fleet is None:
        raise HTTPException(404, detail={"code": "match.not_found"})
    try:
        match = match_for_fleet(session, match_id, fleet)
    except MatchCreationError as error:
        raise _error(error) from error
    return _response(session, match)
