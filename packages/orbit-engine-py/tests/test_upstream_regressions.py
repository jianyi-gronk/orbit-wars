"""Selected 2P regressions adapted from the audited upstream test suite."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

from orbit_engine import OrbitEngine, _pinned_kernel


def make_state(
    planets: list[list[int | float]],
    fleets: list[list[int | float]],
    *,
    step: int = 1,
) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            observation=SimpleNamespace(
                step=step,
                planets=planets,
                fleets=fleets,
                next_fleet_id=100,
                angular_velocity=0.01,
                initial_planets=[planet[:] for planet in planets],
                comets=[],
                comet_planet_ids=[],
            ),
            action=[],
            status="ACTIVE",
            reward=0,
        ),
        SimpleNamespace(
            observation=SimpleNamespace(player=1),
            action=[],
            status="ACTIVE",
            reward=0,
        ),
    ]


def run_kernel(
    state: list[SimpleNamespace],
    *,
    ship_speed: float = 6.0,
) -> list[Any]:
    environment = SimpleNamespace(
        configuration=SimpleNamespace(
            shipSpeed=ship_speed,
            episodeSteps=500,
            cometSpeed=4.0,
        ),
        done=False,
        info={},
    )
    return _pinned_kernel.interpreter(state, environment)  # type: ignore[no-untyped-call]


def test_upstream_map_symmetry_regression() -> None:
    planets = OrbitEngine().reset(seed=9_101).planets

    assert len(planets) >= 4
    assert len(planets) % 4 == 0
    for index in range(0, len(planets), 4):
        first = planets[index]
        opposite = planets[index + 3]
        assert math.isclose(first.x + opposite.x, 100.0, abs_tol=1e-5)
        assert math.isclose(first.y + opposite.y, 100.0, abs_tol=1e-5)
        assert first.radius == opposite.radius


def test_upstream_swept_collision_regression() -> None:
    state = make_state(
        [[0, -1, 50.0, 52.0, 1.0, 10, 0]],
        [[0, 0, 49.0, 50.0, 0.0, 1, 1000]],
    )
    state[0].observation.angular_velocity = math.pi

    result = run_kernel(state, ship_speed=2.0)
    observation = result[0].observation

    assert observation.fleets == []
    assert observation.planets[0][1] == 0
    assert observation.planets[0][5] == 990


def test_upstream_combat_capture_regression() -> None:
    result = run_kernel(
        make_state(
            [[0, -1, 80, 50, 3, 10, 1]],
            [[0, 0, 76.0, 50.0, 0.0, 99, 30]],
        )
    )
    planet = result[0].observation.planets[0]

    assert planet[1] == 0
    assert planet[5] == 20


def test_upstream_step_limit_reward_regression() -> None:
    result = run_kernel(
        make_state(
            [
                [0, 0, 80, 80, 3, 50, 1],
                [1, 1, 20, 20, 3, 30, 1],
            ],
            [],
            step=498,
        )
    )

    assert [state.reward for state in result] == [1, -1]
    assert [state.status for state in result] == ["DONE", "DONE"]
