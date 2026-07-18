"""Conservative training opponent that favors low-garrison neutral planets."""

import math
from typing import Any


def agent(obs: dict[str, Any]) -> list[list[int | float]]:
    player = int(obs.get("player", 0))
    planets = obs.get("planets", [])
    owned = [planet for planet in planets if int(planet.get("owner", -1)) == player]
    neutral = [planet for planet in planets if int(planet.get("owner", -1)) == -1]
    targets = neutral or [planet for planet in planets if int(planet.get("owner", -1)) != player]
    if not owned or not targets:
        return []
    source = max(owned, key=lambda planet: float(planet.get("ships", 0)))
    target = min(targets, key=lambda planet: float(planet.get("ships", 0)))
    available = int(float(source.get("ships", 0)) * 0.25)
    required = int(float(target.get("ships", 0))) + 2
    ships = min(available, required)
    if ships <= required - 2:
        return []
    angle = (
        math.atan2(
            float(target["y"]) - float(source["y"]),
            float(target["x"]) - float(source["x"]),
        )
        % math.tau
    )
    return [[int(source["id"]), angle, ships]]
