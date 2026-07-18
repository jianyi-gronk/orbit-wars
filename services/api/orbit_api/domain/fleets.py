"""Fleet ownership, profile validation, and persistence rules."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from orbit_api.builtin_strategies.registry import BASIC, KAGGLE_STRUCTURED_V11, BuiltinStrategy
from orbit_api.db.base import utc_now
from orbit_api.db.models import Fleet, StrategyStatus, StrategyVersion, User
from orbit_api.security.oidc import Principal
from orbit_api.security.public_ids import new_public_id


class StrategyTendency(StrEnum):
    EXPANSION = "expansion"
    ASSAULT = "assault"
    DEFENSE = "defense"
    BALANCED = "balanced"


class StrategyTemplate(StrEnum):
    PLATFORM_BASIC = "platform-basic"
    KAGGLE_STRUCTURED_V11 = "kaggle-structured-v11"


class FleetError(Exception):
    """Base class for stable fleet-domain failures."""

    code = "fleet.error"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class FleetAlreadyExistsError(FleetError):
    code = "fleet.already_exists"


class FleetNotFoundError(FleetError):
    code = "fleet.not_found"


class FleetContentError(FleetError):
    code = "fleet.invalid_content"


class EmptyFleetUpdateError(FleetError):
    code = "fleet.empty_update"


@dataclass(frozen=True)
class FleetProfileInput:
    name: str
    commander_code: str
    declaration: str
    strategy_tendency: StrategyTendency
    strategy_template: StrategyTemplate
    style_description: str


_SINGLE_LINE_FIELDS = {"name", "commander_code"}
_FIELD_LENGTHS = {
    "name": (2, 80),
    "commander_code": (2, 40),
    "declaration": (0, 500),
    "style_description": (12, 1200),
}
_SHORT_IDENTITY_PATTERN = re.compile(r"^[\w .'/\-·]+$", re.UNICODE)
_HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_PROTECTED_REFERENCE_PATTERN = re.compile(
    r"(?:star\s*wars|星球大战|jedi|绝地武士|sith|西斯|darth\s*vader|达斯维达|"
    r"skywalker|天行者|millennium\s+falcon|千年隼|x[\s-]*wing|tie\s+fighter|"
    r"stormtrooper|风暴兵|death\s+star|死星)",
    re.IGNORECASE,
)


def _normalize_text(field: str, raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        raise FleetContentError("must be text", field=field)

    value = unicodedata.normalize("NFKC", raw_value).replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\t", " ")
    if field in _SINGLE_LINE_FIELDS:
        value = " ".join(value.split())
    else:
        value = "\n".join(" ".join(line.split()) for line in value.split("\n")).strip()

    if any(
        character != "\n" and unicodedata.category(character).startswith("C") for character in value
    ):
        raise FleetContentError("contains unsupported control characters", field=field)
    minimum, maximum = _FIELD_LENGTHS[field]
    if not minimum <= len(value) <= maximum:
        raise FleetContentError(
            f"must contain {minimum}-{maximum} characters",
            field=field,
        )
    if field in _SINGLE_LINE_FIELDS and not _SHORT_IDENTITY_PATTERN.fullmatch(value):
        raise FleetContentError("contains unsupported characters", field=field)
    if _HTML_TAG_PATTERN.search(value) or _URL_PATTERN.search(value):
        raise FleetContentError("must be plain text without links or markup", field=field)
    if field == "style_description" and _PROTECTED_REFERENCE_PATTERN.search(value):
        raise FleetContentError(
            "must describe an original fleet without protected franchise references",
            field=field,
        )
    return value


def validate_profile(payload: dict[str, Any]) -> FleetProfileInput:
    try:
        tendency = StrategyTendency(payload["strategy_tendency"])
    except (KeyError, TypeError, ValueError) as error:
        raise FleetContentError(
            "must be one of expansion, assault, defense, or balanced",
            field="strategy_tendency",
        ) from error
    try:
        template = StrategyTemplate(
            payload.get("strategy_template", StrategyTemplate.PLATFORM_BASIC.value)
        )
    except (TypeError, ValueError) as error:
        raise FleetContentError(
            "must be platform-basic or kaggle-structured-v11",
            field="strategy_template",
        ) from error

    return FleetProfileInput(
        name=_normalize_text("name", payload.get("name")),
        commander_code=_normalize_text("commander_code", payload.get("commander_code")),
        declaration=_normalize_text("declaration", payload.get("declaration", "")),
        strategy_tendency=tendency,
        strategy_template=template,
        style_description=_normalize_text("style_description", payload.get("style_description")),
    )


def _starter_strategy(template: StrategyTemplate) -> BuiltinStrategy:
    if template is StrategyTemplate.KAGGLE_STRUCTURED_V11:
        return KAGGLE_STRUCTURED_V11
    return BASIC


def validate_patch(payload: dict[str, Any]) -> dict[str, str | StrategyTendency]:
    if not payload:
        raise EmptyFleetUpdateError("at least one editable field is required")

    validated: dict[str, str | StrategyTendency] = {}
    for field, value in payload.items():
        if field == "strategy_tendency":
            try:
                validated[field] = StrategyTendency(value)
            except (TypeError, ValueError) as error:
                raise FleetContentError(
                    "must be one of expansion, assault, defense, or balanced",
                    field=field,
                ) from error
        else:
            validated[field] = _normalize_text(field, value)
    return validated


def _display_name(principal: Principal) -> str | None:
    for claim in ("name", "preferred_username", "email"):
        value = principal.claims.get(claim)
        if isinstance(value, str) and value.strip():
            return unicodedata.normalize("NFKC", value).strip()[:120]
    return None


def _account_for(session: Session, principal: Principal) -> User:
    user = session.scalar(select(User).where(User.oidc_subject == principal.subject))
    if user is not None:
        return user

    user = User(oidc_subject=principal.subject, display_name=_display_name(principal))
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        concurrent_user = session.scalar(select(User).where(User.oidc_subject == principal.subject))
        if concurrent_user is None:
            raise
        return concurrent_user
    return user


def create_fleet(
    session: Session,
    principal: Principal,
    payload: dict[str, Any],
    *,
    provision_basic: bool = True,
) -> Fleet:
    profile = validate_profile(payload)
    user = _account_for(session, principal)
    existing = session.scalar(select(Fleet.id).where(Fleet.owner_user_id == user.id))
    if existing is not None:
        session.rollback()
        raise FleetAlreadyExistsError("this account already has an active fleet")

    fleet = Fleet(
        public_id=new_public_id("fleet"),
        owner_user_id=user.id,
        name=profile.name,
        commander_code=profile.commander_code,
        declaration=profile.declaration,
        strategy_tendency=profile.strategy_tendency.value,
        style_description=profile.style_description,
    )
    session.add(fleet)
    try:
        if provision_basic:
            session.flush()
            selected = _starter_strategy(profile.strategy_template)
            package = selected.package_bytes()
            is_kaggle = profile.strategy_template is StrategyTemplate.KAGGLE_STRUCTURED_V11
            starter = StrategyVersion(
                public_id=new_public_id("strategy"),
                fleet_id=fleet.id,
                content_hash=selected.content_hash,
                object_key=f"builtin://{selected.slug}",
                manifest={
                    "schemaVersion": 1,
                    "entrypoint": selected.entrypoint,
                    "builtin": selected.slug,
                },
                notes="Kaggle Structured Baseline v11"
                if is_kaggle
                else "Platform starter strategy",
                source="kaggle" if is_kaggle else "builtin",
                submitted_by="pilkwang via Kaggle" if is_kaggle else "platform",
                runtime_image=selected.runtime_image,
                package_size_bytes=len(package),
                validation_report={
                    "result": "ready",
                    "checks": ["audited_builtin", "contract", "fixed_match"],
                },
                validated_at=utc_now(),
                status=StrategyStatus.READY,
            )
            session.add(starter)
            session.flush()
            fleet.current_strategy_version_id = starter.id
        session.commit()
    except IntegrityError as error:
        session.rollback()
        owner = session.scalar(select(User).where(User.oidc_subject == principal.subject))
        if owner is not None and session.scalar(
            select(Fleet.id).where(Fleet.owner_user_id == owner.id)
        ):
            raise FleetAlreadyExistsError("this account already has an active fleet") from error
        raise
    session.refresh(fleet)
    return fleet


def get_owned_fleet(session: Session, principal: Principal, public_id: str) -> Fleet:
    fleet = session.scalar(
        select(Fleet)
        .join(User, User.id == Fleet.owner_user_id)
        .where(Fleet.public_id == public_id, User.oidc_subject == principal.subject)
    )
    if fleet is None:
        raise FleetNotFoundError("fleet was not found")
    return fleet


def get_public_fleet(session: Session, public_id: str) -> Fleet:
    fleet = session.scalar(select(Fleet).where(Fleet.public_id == public_id))
    if fleet is None:
        raise FleetNotFoundError("fleet was not found")
    return fleet


def update_fleet(
    session: Session,
    principal: Principal,
    public_id: str,
    payload: dict[str, Any],
) -> Fleet:
    changes = validate_patch(payload)
    fleet = get_owned_fleet(session, principal, public_id)
    for field, value in changes.items():
        setattr(fleet, field, value.value if isinstance(value, StrategyTendency) else value)
    session.commit()
    session.refresh(fleet)
    return fleet
