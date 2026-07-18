"""Low-pressure starter strategy that makes one understandable launch per turn."""

import math
from typing import Any


def agent(obs: dict[str, Any]) -> list[list[int | float]]:
    player = int(obs.get("player", 0))
    planets = obs.get("planets", [])
    owned = [planet for planet in planets if int(planet.get("owner", -1)) == player]
    targets = [planet for planet in planets if int(planet.get("owner", -1)) != player]
    if not owned or not targets:
        return []
    source = max(owned, key=lambda planet: float(planet.get("ships", 0)))
    ships = int(float(source.get("ships", 0)) * 0.35)
    if ships < 4:
        return []
    target = min(
        targets,
        key=lambda planet: (
            (float(planet["x"]) - float(source["x"])) ** 2
            + (float(planet["y"]) - float(source["y"])) ** 2
        ),
    )
    angle = (
        math.atan2(
            float(target["y"]) - float(source["y"]),
            float(target["x"]) - float(source["x"]),
        )
        % math.tau
    )
    return [[int(source["id"]), angle, ships]]
