"""Owner-facing in-platform strategy editing, simulation, and publication."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from orbit_api.api.agent import strategy_store
from orbit_api.db.models import StrategyDraft, StrategyVersion
from orbit_api.db.session import database_session
from orbit_api.domain.fleets import FleetError
from orbit_api.domain.simulations import (
    CandidateStrategy,
    SimulationError,
    SimulationRequest,
    create_simulation,
    simulation_response,
)
from orbit_api.domain.strategy_lab import (
    StrategyDraftConflictError,
    StrategyDraftNotValidatedError,
    StrategyLabError,
    StrategyWorkspace,
    get_workspace,
    mark_validated,
    require_validated_package,
    reset_draft,
    update_draft,
)
from orbit_api.domain.strategy_source import build_source_package
from orbit_api.domain.strategy_validation import (
    DockerSandboxSession,
    StrategyValidationError,
    StrategyValidationUnavailable,
    validate_package,
    validate_strategy_version,
)
from orbit_api.domain.strategy_versions import (
    StrategyVersionError,
    publish_strategy_version,
    set_current_strategy,
)
from orbit_api.infrastructure.match_queue import RedisMatchQueue
from orbit_api.security.oidc import Principal, current_principal
from orbit_api.storage.strategy_packages import StrategyPackageStore, StrategyPackageStoreError


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")


class DraftUpdateRequest(APIModel):
    expected_revision: int = Field(ge=1)
    mode: Literal["guided", "code"]
    source_code: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class DraftResetRequest(APIModel):
    expected_revision: int = Field(ge=1)


class LabSimulationRequest(APIModel):
    revision: int = Field(ge=1)
    opponent_id: str = "training-v1"
    idempotency_key: str = Field(min_length=1, max_length=128)


class LabPublishRequest(APIModel):
    revision: int = Field(ge=1)
    notes: str = Field(default="", max_length=1000)
    make_current: bool = True


router = APIRouter(tags=["strategy lab"])
SessionDependency = Annotated[Session, Depends(database_session)]
PrincipalDependency = Annotated[Principal, Depends(current_principal)]
StoreDependency = Annotated[StrategyPackageStore, Depends(strategy_store)]


def _version_response(version: StrategyVersion) -> dict[str, Any]:
    return {
        "publicId": version.public_id,
        "contentHash": version.content_hash,
        "status": version.status,
        "notes": version.notes,
        "source": version.source,
        "submittedBy": version.submitted_by,
        "validation": version.validation_report,
        "createdAt": version.created_at,
    }


def _draft_response(
    draft: StrategyDraft,
    versions: tuple[StrategyVersion, ...],
) -> dict[str, Any]:
    base = next(
        (version for version in versions if version.id == draft.base_strategy_version_id),
        None,
    )
    return {
        "revision": draft.revision,
        "mode": draft.mode,
        "sourceCode": draft.source_code,
        "parameters": draft.parameters,
        "baseStrategyVersionId": base.public_id if base else None,
        "lastValidation": draft.last_validation,
        "validatedContentHash": draft.validated_content_hash,
        "updatedAt": draft.updated_at,
    }


def _workspace_response(workspace: StrategyWorkspace) -> dict[str, Any]:
    current = next(
        (
            version
            for version in workspace.versions
            if version.id == workspace.fleet.current_strategy_version_id
        ),
        None,
    )
    return {
        "fleet": {
            "publicId": workspace.fleet.public_id,
            "name": workspace.fleet.name,
            "currentStrategyVersionId": current.public_id if current else None,
        },
        "draft": _draft_response(workspace.draft, workspace.versions),
        "versions": [_version_response(version) for version in workspace.versions],
        "editableTemplates": [
            {
                "id": "platform-basic",
                "name": "Signal Cadet",
                "editable": True,
                "source": "platform",
            },
            {
                "id": "kaggle-structured-v11",
                "name": "Kaggle Structured v11",
                "editable": False,
                "source": "kaggle",
            },
        ],
        "aiCredits": {
            "remaining": workspace.credits.remaining,
            "granted": workspace.credits.granted,
            "standardCost": 1,
            "deepCost": 2,
        },
    }


def _lab_error(error: Exception) -> HTTPException:
    if isinstance(error, StrategyDraftConflictError):
        response_status = status.HTTP_409_CONFLICT
    elif isinstance(error, StrategyDraftNotValidatedError):
        response_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif isinstance(error, FleetError):
        response_status = status.HTTP_404_NOT_FOUND
    else:
        response_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(
        response_status,
        detail={"code": getattr(error, "code", "strategy_lab.error")},
    )


@router.get("/api/v1/fleets/{fleet_id}/strategy-lab")
def read_workspace(
    fleet_id: str,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, Any]:
    try:
        return _workspace_response(get_workspace(session, principal, fleet_id))
    except (FleetError, StrategyLabError) as error:
        raise _lab_error(error) from error


@router.put("/api/v1/fleets/{fleet_id}/strategy-lab/draft")
def save_draft(
    fleet_id: str,
    payload: DraftUpdateRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, Any]:
    try:
        workspace = update_draft(
            session,
            principal,
            fleet_id,
            expected_revision=payload.expected_revision,
            mode=payload.mode,
            source_code=payload.source_code,
            parameters=payload.parameters,
        )
        return _workspace_response(workspace)
    except (FleetError, StrategyLabError, StrategyVersionError) as error:
        raise _lab_error(error) from error


@router.post("/api/v1/fleets/{fleet_id}/strategy-lab/reset")
def reset_workspace_draft(
    fleet_id: str,
    payload: DraftResetRequest,
    session: SessionDependency,
    principal: PrincipalDependency,
) -> dict[str, Any]:
    try:
        return _workspace_response(
            reset_draft(
                session,
                principal,
                fleet_id,
                expected_revision=payload.expected_revision,
            )
        )
    except (FleetError, StrategyLabError) as error:
        raise _lab_error(error) from error


@router.post("/api/v1/fleets/{fleet_id}/strategy-lab/simulations", status_code=201)
def simulate_draft(
    fleet_id: str,
    payload: LabSimulationRequest,
    request: Request,
    session: SessionDependency,
    principal: PrincipalDependency,
    store: StoreDependency,
) -> dict[str, Any]:
    try:
        workspace = get_workspace(session, principal, fleet_id)
        if workspace.draft.revision != payload.revision:
            raise StrategyDraftConflictError("the strategy draft changed")
        package = build_source_package(workspace.draft.source_code)
        sandbox_factory = getattr(
            request.app.state,
            "strategy_sandbox_factory",
            DockerSandboxSession,
        )
        report = validate_package(
            package.content,
            runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
            sandbox_factory=sandbox_factory,
        )
        object_key = (
            f"fleets/{workspace.fleet.public_id}/simulation-candidates/{package.content_hash}.zip"
        )
        store.put_immutable(object_key, package.content)
        report_json = report.as_json()
        mark_validated(
            session,
            workspace.draft,
            revision=payload.revision,
            report=report_json,
        )
        match, replayed = create_simulation(
            session,
            workspace.fleet,
            SimulationRequest(
                map_id="orbit-standard-v1",
                opponent_type="builtin",
                opponent_id=payload.opponent_id,
            ),
            idempotency_key=payload.idempotency_key,
            actor_key=f"strategy-lab:{principal.subject}",
            candidate=CandidateStrategy(
                content_hash=package.content_hash,
                object_key=object_key,
                manifest=package.manifest,
                runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
                submitted_by="strategy-lab",
                validation=report_json,
            ),
        )
    except (FleetError, StrategyLabError, StrategyValidationError, SimulationError) as error:
        raise _lab_error(error) from error
    except (StrategyValidationUnavailable, StrategyPackageStoreError) as error:
        raise HTTPException(503, detail={"code": "strategy_lab.validation_unavailable"}) from error
    queue = getattr(request.app.state, "match_queue", None)
    if queue is None:
        queue = RedisMatchQueue.from_environment()
        request.app.state.match_queue = queue
    if not replayed:
        queue.enqueue(match.public_id)
    return {**simulation_response(session, match), "idempotentReplay": replayed}


@router.post("/api/v1/fleets/{fleet_id}/strategy-lab/publish", status_code=201)
def publish_draft(
    fleet_id: str,
    payload: LabPublishRequest,
    request: Request,
    session: SessionDependency,
    principal: PrincipalDependency,
    store: StoreDependency,
) -> dict[str, Any]:
    try:
        workspace = get_workspace(session, principal, fleet_id)
        if workspace.draft.revision != payload.revision:
            raise StrategyDraftConflictError("the strategy draft changed")
        package = require_validated_package(workspace.draft)
        publication = publish_strategy_version(
            session,
            store,
            principal,
            fleet_id,
            package,
            notes=payload.notes,
            source="strategy-lab",
            submitted_by="owner",
            runtime_image="orbit-agent-sandbox:py311-stdlib-v1",
        )
        version = publication.version
        if str(version.status) in {"uploaded", "validating"}:
            version = validate_strategy_version(
                session,
                store,
                version.public_id,
                sandbox_factory=getattr(
                    request.app.state,
                    "strategy_sandbox_factory",
                    DockerSandboxSession,
                ),
            )
        if payload.make_current and str(version.status) == "ready":
            version = set_current_strategy(session, principal, fleet_id, version.public_id)
        return {**_version_response(version), "deduplicated": publication.deduplicated}
    except (FleetError, StrategyLabError, StrategyVersionError, StrategyValidationError) as error:
        raise _lab_error(error) from error
    except (StrategyValidationUnavailable, StrategyPackageStoreError) as error:
        raise HTTPException(503, detail={"code": "strategy_lab.validation_unavailable"}) from error
