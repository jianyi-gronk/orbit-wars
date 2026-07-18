/* Generated from schemas/contracts-v1.json. Do not edit by hand. */

/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "ClientMessageV1".
 */
export type ClientMessageV1 = TurnSubmitMessageV1 | MatchResyncMessageV1;
/**
 * @maxItems 6
 */
export type Commands =
  | []
  | [LaunchCommandV1]
  | [LaunchCommandV1, LaunchCommandV1]
  | [LaunchCommandV1, LaunchCommandV1, LaunchCommandV1]
  | [LaunchCommandV1, LaunchCommandV1, LaunchCommandV1, LaunchCommandV1]
  | [LaunchCommandV1, LaunchCommandV1, LaunchCommandV1, LaunchCommandV1, LaunchCommandV1]
  | [
      LaunchCommandV1,
      LaunchCommandV1,
      LaunchCommandV1,
      LaunchCommandV1,
      LaunchCommandV1,
      LaunchCommandV1,
    ];
export type Angle = number;
export type Fromplanetid = number;
export type Ships = number;
export type Expectedstep = number;
export type Idempotencykey = string;
export type Matchid = string;
export type Schemaversion = 1;
export type Type = "turn.submit";
export type Lastseenstep = number;
export type Type1 = "match.resync";
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchMode".
 */
export type MatchMode = "training" | "ranked";
export type Angularvelocity = number;
export type Radius = number;
export type X = number;
export type Y = number;
export type Comets1 = CometV1[];
export type Id = number;
export type Comets = CometGroupV1[];
export type Deadlineat = string;
export type Angle1 = number;
export type Fromplanetid1 = number;
export type Id1 = number;
export type Owner = 0 | 1;
export type Ships1 = number;
export type X1 = number;
export type Y1 = number;
export type Fleets = FleetV1[];
export type Id2 = number;
export type Owner1 = -1 | 0 | 1;
export type Production = number;
export type Radius1 = number;
export type Ships2 = number;
export type X2 = number;
export type Y2 = number;
export type Initialplanets = PlanetV1[];
export type Matchid1 = string;
export type Planets = PlanetV1[];
export type Player = 0 | 1;
export type Schemaversion1 = 1;
export type Step = number;
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "ControllerType".
 */
export type ControllerType = "human" | "agent";
export type Fleetpublicid = string;
export type Slot = 0 | 1;
export type Strategyversionid = string | null;
export type Fleets1 = FleetV1[];
/**
 * @minItems 2
 * @maxItems 2
 */
export type Metrics = [PlayerMetricsV1, PlayerMetricsV1];
export type Intransitships = number;
export type Planets1 = number;
export type Production1 = number;
export type Stationedships = number;
export type Planets2 = PlanetV1[];
export type Schemaversion2 = 1;
export type Step1 = number;
export type Endedat = string;
export type Finalstep = number;
export type Reason = "elimination" | "step_limit" | "forfeit" | "failed";
export type Winnerslot = (0 | 1) | null;
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "ServerMessageV1".
 */
export type ServerMessageV1 =
  | MatchSnapshotMessageV1
  | TurnOpenMessageV1
  | TurnAcceptedMessageV1
  | TurnClosedMessageV1
  | MatchFrameMessageV1
  | MatchFinishedMessageV1
  | MatchErrorMessageV1;
export type Type2 = "match.snapshot";
export type Deadlineat1 = string;
export type Step2 = number;
export type Type3 = "turn.open";
export type Commandhash = string;
export type Step3 = number;
export type Type4 = "turn.accepted";
export type Step4 = number;
export type Type5 = "turn.closed";
export type Type6 = "match.frame";
export type Type7 = "match.finished";
export type Code = string;
export type Recoverable = boolean;
export type Type8 = "match.error";

/**
 * Schema bundle that keeps every public V1 definition reachable.
 */
export interface ContractsV1 {
  clientMessage: ClientMessageV1;
  commandBatch: CommandBatchV1;
  mode: MatchMode;
  observation: ObservationV1;
  participant: MatchParticipantV1;
  replayFrame: ReplayFrameV1;
  result: MatchResultV1;
  serverMessage: ServerMessageV1;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "TurnSubmitMessageV1".
 */
export interface TurnSubmitMessageV1 {
  payload: CommandBatchV1;
  type: Type;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "CommandBatchV1".
 */
export interface CommandBatchV1 {
  commands: Commands;
  expectedStep: Expectedstep;
  idempotencyKey: Idempotencykey;
  matchId: Matchid;
  schemaVersion: Schemaversion;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "LaunchCommandV1".
 */
export interface LaunchCommandV1 {
  angle: Angle;
  fromPlanetId: Fromplanetid;
  ships: Ships;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchResyncMessageV1".
 */
export interface MatchResyncMessageV1 {
  lastSeenStep: Lastseenstep;
  type: Type1;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "ObservationV1".
 */
export interface ObservationV1 {
  angularVelocity: Angularvelocity;
  comets: Comets;
  deadlineAt: Deadlineat;
  fleets: Fleets;
  initialPlanets: Initialplanets;
  matchId: Matchid1;
  planets: Planets;
  player: Player;
  schemaVersion: Schemaversion1;
  step: Step;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "CometGroupV1".
 */
export interface CometGroupV1 {
  comets: Comets1;
  id: Id;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "CometV1".
 */
export interface CometV1 {
  radius: Radius;
  x: X;
  y: Y;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "FleetV1".
 */
export interface FleetV1 {
  angle: Angle1;
  fromPlanetId: Fromplanetid1;
  id: Id1;
  owner: Owner;
  ships: Ships1;
  x: X1;
  y: Y1;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "PlanetV1".
 */
export interface PlanetV1 {
  id: Id2;
  owner: Owner1;
  production: Production;
  radius: Radius1;
  ships: Ships2;
  x: X2;
  y: Y2;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchParticipantV1".
 */
export interface MatchParticipantV1 {
  controllerType: ControllerType;
  fleetPublicId: Fleetpublicid;
  slot: Slot;
  strategyVersionId?: Strategyversionid;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "ReplayFrameV1".
 */
export interface ReplayFrameV1 {
  fleets: Fleets1;
  metrics: Metrics;
  planets: Planets2;
  schemaVersion: Schemaversion2;
  step: Step1;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "PlayerMetricsV1".
 */
export interface PlayerMetricsV1 {
  inTransitShips: Intransitships;
  planets: Planets1;
  production: Production1;
  stationedShips: Stationedships;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchResultV1".
 */
export interface MatchResultV1 {
  endedAt: Endedat;
  finalStep: Finalstep;
  reason: Reason;
  winnerSlot?: Winnerslot;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchSnapshotMessageV1".
 */
export interface MatchSnapshotMessageV1 {
  payload: ObservationV1;
  type: Type2;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "TurnOpenMessageV1".
 */
export interface TurnOpenMessageV1 {
  deadlineAt: Deadlineat1;
  step: Step2;
  type: Type3;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "TurnAcceptedMessageV1".
 */
export interface TurnAcceptedMessageV1 {
  commandHash: Commandhash;
  step: Step3;
  type: Type4;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "TurnClosedMessageV1".
 */
export interface TurnClosedMessageV1 {
  step: Step4;
  type: Type5;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchFrameMessageV1".
 */
export interface MatchFrameMessageV1 {
  payload: ReplayFrameV1;
  type: Type6;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchFinishedMessageV1".
 */
export interface MatchFinishedMessageV1 {
  result: MatchResultV1;
  type: Type7;
}
/**
 * This interface was referenced by `ContractsV1`'s JSON-Schema
 * via the `definition` "MatchErrorMessageV1".
 */
export interface MatchErrorMessageV1 {
  code: Code;
  recoverable: Recoverable;
  type: Type8;
}
