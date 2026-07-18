"""Minimal authenticated account and owned-fleet projections for the Web app."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from orbit_api.db.models import Fleet, StrategyVersion, User
from orbit_api.db.session import database_session
from orbit_api.security.oidc import Principal, current_principal

router = APIRouter(tags=["session"])
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]


@router.get("/api/v1/session")
def read_session(principal: PrincipalDependency) -> dict[str, Any]:
    return {
        "authenticated": True,
        "subject": principal.subject,
        "displayName": next(
            (
                principal.claims.get(key)
                for key in ("name", "preferred_username", "email")
                if isinstance(principal.claims.get(key), str)
            ),
            None,
        ),
    }


@router.get("/api/v1/me/fleet")
def read_my_fleet(
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, Any]:
    fleet = session.scalar(
        select(Fleet)
        .join(User, User.id == Fleet.owner_user_id)
        .where(User.oidc_subject == principal.subject)
    )
    if fleet is None:
        raise HTTPException(404, detail={"code": "fleet.not_found"})
    current = session.get(StrategyVersion, fleet.current_strategy_version_id)
    return {
        "publicId": fleet.public_id,
        "name": fleet.name,
        "commanderCode": fleet.commander_code,
        "declaration": fleet.declaration,
        "strategyTendency": fleet.strategy_tendency,
        "styleDescription": fleet.style_description,
        "currentStrategyVersionId": current.public_id if current else None,
        "createdAt": fleet.created_at,
    }
