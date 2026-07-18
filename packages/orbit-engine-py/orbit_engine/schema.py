"""Stable public data structures for the pinned Orbit Wars engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RulesetConfig:
    episode_steps: int = 500
    ship_speed: float = 6.0
    comet_speed: float = 4.0


@dataclass(frozen=True, slots=True)
class PlanetState:
    id: int
    owner: int
    x: float
    y: float
    radius: float
    ships: int
    production: int

    def to_row(self) -> list[int | float]:
        return [
            self.id,
            self.owner,
            self.x,
            self.y,
            self.radius,
            self.ships,
            self.production,
        ]


@dataclass(frozen=True, slots=True)
class FleetState:
    id: int
    owner: int
    x: float
    y: float
    angle: float
    from_planet_id: int
    ships: int

    def to_row(self) -> list[int | float]:
        return [
            self.id,
            self.owner,
            self.x,
            self.y,
            self.angle,
            self.from_planet_id,
            self.ships,
        ]


@dataclass(frozen=True, slots=True)
class CometGroupState:
    planet_ids: tuple[int, ...]
    paths: tuple[tuple[tuple[float, float], ...], ...]
    path_index: int


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    ruleset_id: str
    config: RulesetConfig
    step: int
    player: int | None
    done: bool
    angular_velocity: float
    planets: tuple[PlanetState, ...]
    fleets: tuple[FleetState, ...]
    initial_planets: tuple[PlanetState, ...]
    next_fleet_id: int
    comets: tuple[CometGroupState, ...]
    comet_planet_ids: tuple[int, ...]
    rewards: tuple[int | None, ...]
    seed_commitment: str
    state_hash: str


@dataclass(frozen=True, slots=True)
class EngineStepResult:
    snapshot: EngineSnapshot
    rewards: tuple[int | None, ...]
    done: bool
