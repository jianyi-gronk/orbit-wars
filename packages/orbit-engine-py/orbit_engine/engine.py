"""Kaggle-independent wrapper around the pinned Orbit Wars 2P rule kernel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import cast

from orbit_engine import _pinned_kernel
from orbit_engine.actions import LaunchCommand, decode_raw_action, encode_action
from orbit_engine.hashing import seed_commitment, state_hash
from orbit_engine.schema import (
    CometGroupState,
    EngineSnapshot,
    EngineStepResult,
    FleetState,
    PlanetState,
    RulesetConfig,
)

PINNED_RULESET_ID = "orbit-wars-2p-v1"
PINNED_CONFIG = RulesetConfig()


class EngineNotInitializedError(RuntimeError):
    pass


class EngineFinishedError(RuntimeError):
    pass


@dataclass(slots=True)
class _RuntimeState:
    observation: SimpleNamespace
    action: list[list[int | float]]
    reward: int | None = 0
    status: str = "ACTIVE"


@dataclass(slots=True)
class _RuntimeEnvironment:
    configuration: SimpleNamespace
    info: dict[str, int]
    done: bool = False


_Interpreter = Callable[
    [list[_RuntimeState], _RuntimeEnvironment],
    list[_RuntimeState],
]
_INTERPRETER = cast(_Interpreter, _pinned_kernel.interpreter)


class OrbitEngine:
    """Deterministic, fixed-ruleset Orbit Wars engine for exactly two players."""

    ruleset_id = PINNED_RULESET_ID

    def __init__(self, config: RulesetConfig | None = None) -> None:
        if config is not None and config != PINNED_CONFIG:
            raise ValueError(
                f"ruleset {self.ruleset_id!r} has immutable configuration {PINNED_CONFIG!r}"
            )
        self.config = PINNED_CONFIG
        self._states: list[_RuntimeState] = []
        self._environment: _RuntimeEnvironment | None = None
        self._seed: int | None = None
        self._step = 0
        self._done = False

    @property
    def done(self) -> bool:
        return self._done

    @property
    def seed(self) -> int:
        """Return the resolved seed for trusted Worker/replay metadata only."""

        if self._seed is None:
            raise EngineNotInitializedError("reset() must be called before reading the seed")
        return self._seed

    def reset(self, *, seed: int, players: int = 2) -> EngineSnapshot:
        if players != 2:
            raise ValueError(f"ruleset {self.ruleset_id!r} supports exactly two players")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")

        observations = [SimpleNamespace(step=0, planets=[]), SimpleNamespace(step=0, planets=[])]
        self._states = [_RuntimeState(observation=obs, action=[]) for obs in observations]
        self._environment = _RuntimeEnvironment(
            configuration=SimpleNamespace(
                seed=seed,
                episodeSteps=self.config.episode_steps,
                shipSpeed=self.config.ship_speed,
                cometSpeed=self.config.comet_speed,
            ),
            info={},
        )
        self._seed = seed
        self._step = 0
        self._done = False
        _INTERPRETER(self._states, self._environment)
        return self.snapshot()

    def step(self, actions: list[list[LaunchCommand]]) -> EngineStepResult:
        if self._environment is None or not self._states:
            raise EngineNotInitializedError("reset() must be called before step()")
        if self._done:
            raise EngineFinishedError("the match is already finished")
        if len(actions) != 2:
            raise ValueError("exactly one action batch is required for each of two players")

        for index, commands in enumerate(actions):
            self._states[index].action = encode_action(commands)
            self._states[index].observation.step = self._step

        _INTERPRETER(self._states, self._environment)
        self._step += 1
        for state in self._states:
            state.observation.step = self._step
        self._done = all(state.status == "DONE" for state in self._states)
        self._environment.done = self._done
        snapshot = self.snapshot()
        return EngineStepResult(snapshot=snapshot, rewards=snapshot.rewards, done=self._done)

    def step_raw(self, actions: object) -> EngineStepResult:
        """Validate and execute two batches in the original nested-list format."""

        if not isinstance(actions, (list, tuple)) or len(actions) != 2:
            raise ValueError("exactly two legacy action batches are required")
        decoded = [decode_raw_action(actions[0]), decode_raw_action(actions[1])]
        return self.step(decoded)

    def snapshot(self, *, player: int | None = None) -> EngineSnapshot:
        if self._environment is None or not self._states or self._seed is None:
            raise EngineNotInitializedError("reset() must be called before snapshot()")
        if player not in (None, 0, 1):
            raise ValueError("player must be 0, 1, or None")

        observation = self._states[0].observation
        snapshot = EngineSnapshot(
            ruleset_id=self.ruleset_id,
            config=self.config,
            step=self._step,
            player=player,
            done=self._done,
            angular_velocity=float(observation.angular_velocity),
            planets=self._planet_states(observation.planets),
            fleets=self._fleet_states(observation.fleets),
            initial_planets=self._planet_states(observation.initial_planets),
            next_fleet_id=int(observation.next_fleet_id),
            comets=self._comet_states(observation.comets),
            comet_planet_ids=tuple(cast(list[int], observation.comet_planet_ids)),
            rewards=tuple(state.reward for state in self._states),
            seed_commitment=seed_commitment(self.ruleset_id, self._seed),
            state_hash="",
        )
        return replace(snapshot, state_hash=state_hash(snapshot))

    @staticmethod
    def _planet_states(value: object) -> tuple[PlanetState, ...]:
        rows = cast(list[list[int | float]], value)
        return tuple(
            PlanetState(
                id=int(row[0]),
                owner=int(row[1]),
                x=float(row[2]),
                y=float(row[3]),
                radius=float(row[4]),
                ships=int(row[5]),
                production=int(row[6]),
            )
            for row in rows
        )

    @staticmethod
    def _fleet_states(value: object) -> tuple[FleetState, ...]:
        rows = cast(list[list[int | float]], value)
        return tuple(
            FleetState(
                id=int(row[0]),
                owner=int(row[1]),
                x=float(row[2]),
                y=float(row[3]),
                angle=float(row[4]),
                from_planet_id=int(row[5]),
                ships=int(row[6]),
            )
            for row in rows
        )

    @staticmethod
    def _comet_states(value: object) -> tuple[CometGroupState, ...]:
        groups = cast(list[dict[str, object]], value)
        result: list[CometGroupState] = []
        for group in groups:
            raw_paths = cast(list[list[list[float]]], group["paths"])
            paths = tuple(
                tuple((float(point[0]), float(point[1])) for point in path) for path in raw_paths
            )
            result.append(
                CometGroupState(
                    planet_ids=tuple(cast(list[int], group["planet_ids"])),
                    paths=paths,
                    path_index=int(cast(int, group["path_index"])),
                )
            )
        return tuple(result)
