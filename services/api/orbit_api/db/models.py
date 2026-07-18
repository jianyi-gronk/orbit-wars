"""Phase-one persistence model."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from orbit_api.db.base import Base, utc_now
from orbit_api.security.public_ids import new_public_id


class StrategyStatus(StrEnum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    READY = "ready"
    REJECTED = "rejected"


class MatchStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    FINALIZING = "finalizing"
    FINISHED = "finished"
    FAILED = "failed"
    FORFEITED = "forfeited"
    CANCELLED = "cancelled"


class MatchMode(StrEnum):
    TRAINING = "training"
    RANKED = "ranked"


class ControllerType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    oidc_subject: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Fleet(Base):
    __tablename__ = "fleets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: new_public_id("fleet")
    )
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    commander_code: Mapped[str] = mapped_column(String(40))
    declaration: Mapped[str] = mapped_column(Text, default="")
    style_description: Mapped[str] = mapped_column(Text, default="")
    strategy_tendency: Mapped[str] = mapped_column(String(24), default="balanced")
    current_strategy_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id", use_alter=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentKey(Base):
    __tablename__ = "agent_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), index=True)
    public_prefix: Mapped[str] = mapped_column(String(32), unique=True)
    secret_digest: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("fleet_id", "content_hash"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: new_public_id("strategy")
    )
    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255))
    submitted_by: Mapped[str] = mapped_column(String(120))
    runtime_image: Mapped[str] = mapped_column(String(255))
    package_size_bytes: Mapped[int] = mapped_column(Integer)
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, native_enum=False, length=24), default=StrategyStatus.UPLOADED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StrategyDraft(Base):
    __tablename__ = "strategy_drafts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), unique=True, index=True)
    base_strategy_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("strategy_versions.id")
    )
    source_code: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16), default="guided")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    last_validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validated_content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AiCreditAccount(Base):
    __tablename__ = "ai_credit_accounts"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    remaining: Mapped[int] = mapped_column(Integer, default=30)
    granted: Mapped[int] = mapped_column(Integer, default=30)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AiAssistRequest(Base):
    __tablename__ = "ai_assist_requests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: new_public_id("assist")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), index=True)
    draft_revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    cost: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="reserved", index=True)
    model: Mapped[str] = mapped_column(String(80), default="deepseek-v4-flash")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: new_public_id("match")
    )
    ruleset_id: Mapped[str] = mapped_column(String(80))
    map_id: Mapped[str] = mapped_column(String(64), default="orbit-standard-v1")
    seed: Mapped[int] = mapped_column(BigInteger)
    request_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    matchmaking_reason: Mapped[str | None] = mapped_column(String(255))
    rating_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    mode: Mapped[MatchMode] = mapped_column(Enum(MatchMode, native_enum=False, length=16))
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus, native_enum=False, length=24))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    replay_id: Mapped[UUID | None] = mapped_column(ForeignKey("replay_artifacts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (UniqueConstraint("match_id", "slot"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    controller_type: Mapped[ControllerType] = mapped_column(
        Enum(ControllerType, native_enum=False, length=16)
    )
    strategy_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("strategy_versions.id"))
    candidate_content_hash: Mapped[str | None] = mapped_column(String(64))
    candidate_object_key: Mapped[str | None] = mapped_column(String(512))
    candidate_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    candidate_runtime_image: Mapped[str | None] = mapped_column(String(255))
    candidate_submitted_by: Mapped[str | None] = mapped_column(String(120))
    candidate_validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class MatchCommand(Base):
    __tablename__ = "match_commands"
    __table_args__ = (UniqueConstraint("match_id", "step", "slot"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer)
    command_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid: Mapped[bool] = mapped_column(Boolean)


class Rating(Base):
    __tablename__ = "ratings"

    fleet_id: Mapped[UUID] = mapped_column(ForeignKey("fleets.id"), primary_key=True)
    mu: Mapped[float] = mapped_column(Float, default=25.0)
    sigma: Mapped[float] = mapped_column(Float, default=25.0 / 3.0)
    display_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RatingEvent(Base):
    __tablename__ = "rating_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id"), unique=True, index=True)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReplayArtifact(Base):
    __tablename__ = "replay_artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=lambda: new_public_id("replay")
    )
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analysis_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(12))
    path: Mapped[str] = mapped_column(String(512))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
