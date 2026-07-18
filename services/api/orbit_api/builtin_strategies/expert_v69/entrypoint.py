"""Convert the public object contract to the legacy row format consumed by v69."""

from main import agent as v69_agent


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
    converted["next_fleet_id"] = (
        max((int(fleet[0]) for fleet in converted["fleets"]), default=-1) + 1
    )
    return v69_agent(converted)


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
