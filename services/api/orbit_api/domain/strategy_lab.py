"""Private editable strategy drafts for owner-facing in-platform iteration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.db.base import utc_now
from orbit_api.db.models import (
    AiCreditAccount,
    Fleet,
    StrategyDraft,
    StrategyVersion,
)
from orbit_api.domain.fleets import get_owned_fleet
from orbit_api.domain.strategy_source import (
    DEFAULT_PARAMETERS,
    build_source_package,
    guided_source,
    platform_basic_source,
    validate_source,
)
from orbit_api.security.oidc import Principal


class StrategyLabError(RuntimeError):
    code = "strategy_lab.error"


class StrategyDraftConflictError(StrategyLabError):
    code = "strategy_lab.revision_conflict"


class StrategyDraftInvalidError(StrategyLabError):
    code = "strategy_lab.invalid_draft"


class StrategyDraftNotValidatedError(StrategyLabError):
    code = "strategy_lab.not_validated"


@dataclass(frozen=True)
class StrategyWorkspace:
    fleet: Fleet
    draft: StrategyDraft
    versions: tuple[StrategyVersion, ...]
    credits: AiCreditAccount


def _free_credits() -> int:
    try:
        return max(0, int(os.environ.get("ORBIT_AI_FREE_CREDITS", "30")))
    except ValueError:
        return 30


def _initial_draft(fleet: Fleet) -> StrategyDraft:
    parameters = dict(DEFAULT_PARAMETERS)
    return StrategyDraft(
        fleet_id=fleet.id,
        base_strategy_version_id=fleet.current_strategy_version_id,
        source_code=guided_source(
            float(parameters["launchRatio"]),
            int(parameters["minimumShips"]),
            str(parameters["targetPreference"]),  # type: ignore[arg-type]
        ),
        mode="guided",
        parameters=parameters,
        revision=1,
    )


def get_workspace(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
) -> StrategyWorkspace:
    fleet = get_owned_fleet(session, principal, fleet_public_id)
    draft = session.scalar(select(StrategyDraft).where(StrategyDraft.fleet_id == fleet.id))
    credits = session.get(AiCreditAccount, fleet.owner_user_id)
    created = False
    if draft is None:
        draft = _initial_draft(fleet)
        session.add(draft)
        created = True
    if credits is None:
        grant = _free_credits()
        credits = AiCreditAccount(
            user_id=fleet.owner_user_id,
            remaining=grant,
            granted=grant,
        )
        session.add(credits)
        created = True
    if created:
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            draft = session.scalar(
                select(StrategyDraft).where(StrategyDraft.fleet_id == fleet.id)
            )
            credits = session.get(AiCreditAccount, fleet.owner_user_id)
            if draft is None or credits is None:
                raise
        session.refresh(draft)
        session.refresh(credits)
    versions = tuple(
        session.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.fleet_id == fleet.id)
            .order_by(StrategyVersion.created_at.desc())
        )
    )
    return StrategyWorkspace(fleet, draft, versions, credits)


def _guided_parameters(values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        launch_ratio = min(0.9, max(0.1, float(values.get("launchRatio", 0.35))))
        minimum_ships = min(100, max(1, int(values.get("minimumShips", 4))))
        target = str(values.get("targetPreference", "nearest"))
    except (TypeError, ValueError) as error:
        raise StrategyDraftInvalidError("guided parameters are invalid") from error
    if target not in {"nearest", "weakest"}:
        raise StrategyDraftInvalidError("targetPreference must be nearest or weakest")
    parameters = {
        "launchRatio": launch_ratio,
        "minimumShips": minimum_ships,
        "targetPreference": target,
    }
    source = guided_source(launch_ratio, minimum_ships, target)  # type: ignore[arg-type]
    return parameters, source


def update_draft(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
    *,
    expected_revision: int,
    mode: Literal["guided", "code"],
    source_code: str,
    parameters: dict[str, Any],
) -> StrategyWorkspace:
    workspace = get_workspace(session, principal, fleet_public_id)
    draft = workspace.draft
    if draft.revision != expected_revision:
        raise StrategyDraftConflictError("the strategy draft changed in another session")
    if mode == "guided":
        normalized_parameters, normalized_source = _guided_parameters(parameters)
    else:
        validate_source(source_code)
        normalized_parameters = dict(parameters)
        normalized_source = source_code
    draft.mode = mode
    draft.parameters = normalized_parameters
    draft.source_code = normalized_source
    draft.revision += 1
    draft.last_validation = None
    draft.validated_content_hash = None
    draft.updated_at = utc_now()
    session.commit()
    session.refresh(draft)
    return StrategyWorkspace(workspace.fleet, draft, workspace.versions, workspace.credits)


def reset_draft(
    session: Session,
    principal: Principal,
    fleet_public_id: str,
    *,
    expected_revision: int,
) -> StrategyWorkspace:
    workspace = get_workspace(session, principal, fleet_public_id)
    if workspace.draft.revision != expected_revision:
        raise StrategyDraftConflictError("the strategy draft changed in another session")
    workspace.draft.source_code = platform_basic_source()
    workspace.draft.mode = "code"
    workspace.draft.parameters = dict(DEFAULT_PARAMETERS)
    workspace.draft.base_strategy_version_id = workspace.fleet.current_strategy_version_id
    workspace.draft.revision += 1
    workspace.draft.last_validation = None
    workspace.draft.validated_content_hash = None
    workspace.draft.updated_at = utc_now()
    session.commit()
    session.refresh(workspace.draft)
    return workspace


def mark_validated(
    session: Session,
    draft: StrategyDraft,
    *,
    revision: int,
    report: dict[str, Any],
) -> str:
    if draft.revision != revision:
        raise StrategyDraftConflictError("the strategy draft changed before validation completed")
    content_hash = build_source_package(draft.source_code).content_hash
    draft.last_validation = report
    draft.validated_content_hash = content_hash
    draft.updated_at = utc_now()
    session.commit()
    session.refresh(draft)
    return content_hash


def require_validated_package(draft: StrategyDraft) -> bytes:
    package = build_source_package(draft.source_code)
    if draft.validated_content_hash != package.content_hash:
        raise StrategyDraftNotValidatedError("the current draft must pass simulation validation")
    return package.content
