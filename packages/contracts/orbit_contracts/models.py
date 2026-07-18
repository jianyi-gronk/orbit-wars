"""Pydantic source of truth for schema version 1."""

from datetime import datetime
from enum import StrEnum
from math import tau
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, RootModel
from pydantic.alias_generators import to_camel

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveShips = Annotated[int, Field(gt=0)]
NonNegativeNumber = Annotated[FiniteFloat, Field(ge=0)]
AngleRadians = Annotated[FiniteFloat, Field(ge=0, lt=tau)]


class ContractModel(BaseModel):
    """Strict camelCase model shared by all public contracts."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        strict=True,
        use_enum_values=True,
    )


class ControllerType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class MatchMode(StrEnum):
    TRAINING = "training"
    RANKED = "ranked"


class PlanetV1(ContractModel):
    id: NonNegativeInt
    owner: Literal[-1, 0, 1]
    x: FiniteFloat
    y: FiniteFloat
    radius: Annotated[FiniteFloat, Field(gt=0)]
    ships: NonNegativeNumber
    production: NonNegativeNumber


class FleetV1(ContractModel):
    id: NonNegativeInt
    owner: Literal[0, 1]
    x: FiniteFloat
    y: FiniteFloat
    angle: AngleRadians
    from_planet_id: NonNegativeInt
    ships: NonNegativeNumber


class CometV1(ContractModel):
    x: FiniteFloat
    y: FiniteFloat
    radius: Annotated[FiniteFloat, Field(gt=0)]


class CometGroupV1(ContractModel):
    id: NonNegativeInt
    comets: list[CometV1]


class ObservationV1(ContractModel):
    schema_version: Literal[1]
    match_id: Annotated[str, Field(min_length=1, max_length=128)]
    step: NonNegativeInt
    player: Literal[0, 1]
    deadline_at: datetime
    angular_velocity: FiniteFloat
    planets: list[PlanetV1]
    fleets: list[FleetV1]
    initial_planets: list[PlanetV1]
    comets: list[CometGroupV1]


class LaunchCommandV1(ContractModel):
    from_planet_id: NonNegativeInt
    angle: AngleRadians
    ships: PositiveShips


class CommandBatchV1(ContractModel):
    schema_version: Literal[1]
    match_id: Annotated[str, Field(min_length=1, max_length=128)]
    expected_step: NonNegativeInt
    commands: Annotated[list[LaunchCommandV1], Field(max_length=6)]
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]


class MatchParticipantV1(ContractModel):
    fleet_public_id: Annotated[str, Field(min_length=1, max_length=128)]
    slot: Literal[0, 1]
    controller_type: ControllerType
    strategy_version_id: str | None = None


class MatchResultV1(ContractModel):
    winner_slot: Literal[0, 1] | None = None
    reason: Literal["elimination", "step_limit", "forfeit", "failed"]
    final_step: NonNegativeInt
    ended_at: datetime


class PlayerMetricsV1(ContractModel):
    planets: NonNegativeInt
    production: NonNegativeNumber
    stationed_ships: NonNegativeNumber
    in_transit_ships: NonNegativeNumber


class ReplayFrameV1(ContractModel):
    schema_version: Literal[1]
    step: NonNegativeInt
    planets: list[PlanetV1]
    fleets: list[FleetV1]
    metrics: Annotated[list[PlayerMetricsV1], Field(min_length=2, max_length=2)]


class MatchSnapshotMessageV1(ContractModel):
    type: Literal["match.snapshot"]
    payload: ObservationV1


class TurnOpenMessageV1(ContractModel):
    type: Literal["turn.open"]
    step: NonNegativeInt
    deadline_at: datetime


class TurnAcceptedMessageV1(ContractModel):
    type: Literal["turn.accepted"]
    step: NonNegativeInt
    command_hash: Annotated[str, Field(min_length=64, max_length=64)]


class TurnClosedMessageV1(ContractModel):
    type: Literal["turn.closed"]
    step: NonNegativeInt


class MatchFrameMessageV1(ContractModel):
    type: Literal["match.frame"]
    payload: ReplayFrameV1


class MatchFinishedMessageV1(ContractModel):
    type: Literal["match.finished"]
    result: MatchResultV1


class MatchErrorMessageV1(ContractModel):
    type: Literal["match.error"]
    code: Annotated[str, Field(min_length=1, max_length=64)]
    recoverable: bool


ServerMessage = Annotated[
    MatchSnapshotMessageV1
    | TurnOpenMessageV1
    | TurnAcceptedMessageV1
    | TurnClosedMessageV1
    | MatchFrameMessageV1
    | MatchFinishedMessageV1
    | MatchErrorMessageV1,
    Field(discriminator="type"),
]


class ServerMessageV1(RootModel[ServerMessage]):
    pass


class TurnSubmitMessageV1(ContractModel):
    type: Literal["turn.submit"]
    payload: CommandBatchV1


class MatchResyncMessageV1(ContractModel):
    type: Literal["match.resync"]
    last_seen_step: NonNegativeInt


ClientMessage = Annotated[
    TurnSubmitMessageV1 | MatchResyncMessageV1,
    Field(discriminator="type"),
]


class ClientMessageV1(RootModel[ClientMessage]):
    pass


class ContractsV1(ContractModel):
    """Schema bundle that keeps every public V1 definition reachable."""

    observation: ObservationV1
    command_batch: CommandBatchV1
    participant: MatchParticipantV1
    result: MatchResultV1
    replay_frame: ReplayFrameV1
    server_message: ServerMessageV1
    client_message: ClientMessageV1
    mode: MatchMode
