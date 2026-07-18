"""Authenticated fleet management and public profile routes."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from orbit_api.db.models import Fleet
from orbit_api.db.session import database_session
from orbit_api.domain.fleets import (
    EmptyFleetUpdateError,
    FleetAlreadyExistsError,
    FleetContentError,
    FleetError,
    FleetNotFoundError,
    StrategyTemplate,
    StrategyTendency,
    create_fleet,
    get_owned_fleet,
    get_public_fleet,
    update_fleet,
)
from orbit_api.security.oidc import Principal, current_principal


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        populate_by_name=True,
        extra="forbid",
    )


class FleetCreateRequest(APIModel):
    name: str
    commander_code: str
    declaration: str = ""
    strategy_tendency: StrategyTendency = StrategyTendency.BALANCED
    strategy_template: StrategyTemplate = StrategyTemplate.PLATFORM_BASIC
    style_description: str


class FleetPatchRequest(APIModel):
    name: str | None = None
    commander_code: str | None = None
    declaration: str | None = None
    strategy_tendency: StrategyTendency | None = None
    style_description: str | None = None


class FleetProfileResponse(APIModel):
    public_id: str
    name: str
    commander_code: str
    declaration: str
    strategy_tendency: StrategyTendency
    style_description: str
    created_at: datetime

    @classmethod
    def from_fleet(cls, fleet: Fleet) -> "FleetProfileResponse":
        return cls(
            public_id=fleet.public_id,
            name=fleet.name,
            commander_code=fleet.commander_code,
            declaration=fleet.declaration,
            strategy_tendency=StrategyTendency(fleet.strategy_tendency),
            style_description=fleet.style_description,
            created_at=fleet.created_at,
        )


router = APIRouter()
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


def _payload(model: APIModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    return model.model_dump(exclude_unset=exclude_unset, mode="json")


def _http_error(error: FleetError) -> HTTPException:
    detail: dict[str, str] = {"code": error.code, "message": error.message}
    if error.field is not None:
        detail["field"] = _camel_case(error.field)

    if isinstance(error, FleetAlreadyExistsError):
        response_status = status.HTTP_409_CONFLICT
    elif isinstance(error, FleetNotFoundError):
        response_status = status.HTTP_404_NOT_FOUND
    elif isinstance(error, (FleetContentError, EmptyFleetUpdateError)):
        response_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=response_status, detail=detail)


@router.post(
    "/api/v1/fleets",
    response_model=FleetProfileResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["fleets"],
)
def create_fleet_route(
    request: FleetCreateRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> FleetProfileResponse:
    try:
        fleet = create_fleet(session, principal, _payload(request))
    except FleetError as error:
        raise _http_error(error) from error
    return FleetProfileResponse.from_fleet(fleet)


@router.get(
    "/api/v1/fleets/{public_id}",
    response_model=FleetProfileResponse,
    tags=["fleets"],
)
def read_owned_fleet_route(
    public_id: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> FleetProfileResponse:
    try:
        fleet = get_owned_fleet(session, principal, public_id)
    except FleetError as error:
        raise _http_error(error) from error
    return FleetProfileResponse.from_fleet(fleet)


@router.patch(
    "/api/v1/fleets/{public_id}",
    response_model=FleetProfileResponse,
    tags=["fleets"],
)
def update_fleet_route(
    public_id: str,
    request: FleetPatchRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> FleetProfileResponse:
    try:
        fleet = update_fleet(
            session,
            principal,
            public_id,
            _payload(request, exclude_unset=True),
        )
    except FleetError as error:
        raise _http_error(error) from error
    return FleetProfileResponse.from_fleet(fleet)


@router.get(
    "/api/public/v1/fleets/{public_id}",
    response_model=FleetProfileResponse,
    tags=["public fleets"],
)
def read_public_fleet_route(
    public_id: str,
    session: SessionDependency,
) -> FleetProfileResponse:
    try:
        fleet = get_public_fleet(session, public_id)
    except FleetError as error:
        raise _http_error(error) from error
    return FleetProfileResponse.from_fleet(fleet)
