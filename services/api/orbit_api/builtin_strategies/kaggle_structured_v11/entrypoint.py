"""Adapt Orbit/Wars' public object contract to the Kaggle row contract."""

import math

try:
    from .main import agent as kaggle_agent
except ImportError:  # Loaded from the root of the immutable strategy package.
    from main import agent as kaggle_agent


def agent(observation: dict):
    converted = dict(observation)
    converted["angular_velocity"] = observation.get("angularVelocity", 0.03)
    converted["initial_planets"] = [
        _planet_row(planet) for planet in observation.get("initialPlanets", [])
    ]
    converted["planets"] = [_planet_row(planet) for planet in observation.get("planets", [])]
    converted["fleets"] = [_fleet_row(fleet) for fleet in observation.get("fleets", [])]
    converted["comets"] = []
    converted["comet_planet_ids"] = []
    converted["episode_steps"] = 500
    converted["remainingOverageTime"] = 2.0
    actions = kaggle_agent(converted)
    return [
        [int(source), float(angle) % math.tau, int(ships)]
        for source, angle, ships in actions[:6]
    ]


def _planet_row(planet: dict):
    return [
        planet["id"],
        planet["owner"],
        planet["x"],
        planet["y"],
        planet["radius"],
        planet["ships"],
        planet["production"],
    ]


def _fleet_row(fleet: dict):
    return [
        fleet["id"],
        fleet["owner"],
        fleet["x"],
        fleet["y"],
        fleet["angle"],
        fleet["fromPlanetId"],
        fleet["ships"],
    ]
