"""Owner-facing training simulation endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from orbit_api.api.agent import SlidingWindowLimiter
from orbit_api.db.session import database_session
from orbit_api.domain.fleets import FleetError, get_owned_fleet
from orbit_api.domain.simulations import (
    MAPS,
    SimulationConflictError,
    SimulationError,
    SimulationRequest,
    create_simulation,
    get_simulation,
    simulation_response,
)
from orbit_api.infrastructure.match_queue import RedisMatchQueue
from orbit_api.security.oidc import Principal, current_principal


class SimulationCreateBody(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0] + "".join(part.capitalize() for part in value.split("_")[1:])
        ),
        populate_by_name=True,
        extra="forbid",
    )
    map_id: str = "orbit-standard-v1"
    opponent_type: Literal["builtin", "public"] = "builtin"
    opponent_id: str = "training-v1"
    strategy_version_id: str | None = None
    idempotency_key: str | None = None


router = APIRouter(tags=["simulations"])
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]
_default_limiter = SlidingWindowLimiter(limit=10, window_seconds=60)


def _limit(request: Request, fleet_id: str, actor: str) -> None:
    limiter = getattr(request.app.state, "simulation_rate_limiter", _default_limiter)
    if not limiter.allow(f"fleet:{fleet_id}") or not limiter.allow(f"actor:{actor}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "simulation.rate_limited"},
            headers={"Retry-After": "60"},
        )


def _error(error: SimulationError) -> HTTPException:
    response_status = 409 if isinstance(error, SimulationConflictError) else 422
    if error.code == "simulation.not_found":
        response_status = 404
    return HTTPException(response_status, detail={"code": error.code, "message": str(error)})


@router.get("/api/public/v1/simulation-maps")
def maps() -> list[dict[str, str]]:
    return [{"id": map_id, **metadata} for map_id, metadata in MAPS.items()]


@router.post("/api/v1/fleets/{fleet_id}/simulations", status_code=201)
def create_owner_simulation(
    fleet_id: str,
    payload: SimulationCreateBody,
    request: Request,
    session: SessionDependency,
    principal: PrincipalDependency,
    header_idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    try:
        fleet = get_owned_fleet(session, principal, fleet_id)
        _limit(request, str(fleet.id), principal.subject)
        match, replayed = create_simulation(
            session,
            fleet,
            SimulationRequest(**payload.model_dump(exclude={"idempotency_key"})),
            idempotency_key=header_idempotency_key or payload.idempotency_key or "",
            actor_key=f"owner:{principal.subject}",
        )
    except FleetError as error:
        raise HTTPException(404, detail={"code": error.code}) from error
    except SimulationError as error:
        raise _error(error) from error
    queue = getattr(request.app.state, "match_queue", None)
    if queue is None:
        queue = RedisMatchQueue.from_environment()
        request.app.state.match_queue = queue
    if not replayed:
        queue.enqueue(match.public_id)
    return {**simulation_response(session, match), "idempotentReplay": replayed}


@router.get("/api/v1/fleets/{fleet_id}/simulations/{simulation_id}")
def read_owner_simulation(
    fleet_id: str,
    simulation_id: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, object]:
    try:
        fleet = get_owned_fleet(session, principal, fleet_id)
        return simulation_response(session, get_simulation(session, fleet, simulation_id))
    except FleetError as error:
        raise HTTPException(404, detail={"code": error.code}) from error
    except SimulationError as error:
        raise _error(error) from error
