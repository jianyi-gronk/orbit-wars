"""Adapters for the original Orbit Wars launch action format."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

RawScalar: TypeAlias = int | float
RawLaunchCommand: TypeAlias = list[RawScalar]
RawAction: TypeAlias = list[RawLaunchCommand]


class ActionFormatError(ValueError):
    """Raised when an action cannot be represented by the pinned engine."""


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    """A validated launch command with a lossless legacy representation."""

    from_planet_id: int
    angle: float
    ships: int

    def __post_init__(self) -> None:
        if isinstance(self.from_planet_id, bool):
            raise ActionFormatError("from_planet_id must be an integer")
        if isinstance(self.ships, bool) or self.ships <= 0:
            raise ActionFormatError("ships must be a positive integer")
        if not math.isfinite(self.angle):
            raise ActionFormatError("angle must be finite")

    def to_raw(self) -> RawLaunchCommand:
        """Return the original ``[planet_id, angle, ships]`` representation."""

        return [self.from_planet_id, self.angle, self.ships]

    @classmethod
    def from_raw(cls, value: object) -> LaunchCommand:
        """Parse one legacy command without changing its engine semantics.

        Historical Kaggle replays occasionally encode integral IDs or ship
        counts as JSON floats. The original interpreter accepted those values,
        so this adapter canonicalizes them to integers before contract export.
        """

        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ActionFormatError("each launch command must contain exactly three values")
        from_planet_id, angle, ships = value
        if isinstance(from_planet_id, bool) or not isinstance(from_planet_id, (int, float)):
            raise ActionFormatError("from_planet_id must be an integer")
        if not math.isfinite(from_planet_id) or not float(from_planet_id).is_integer():
            raise ActionFormatError("from_planet_id must be an integer")
        if isinstance(angle, bool) or not isinstance(angle, (int, float)):
            raise ActionFormatError("angle must be a finite number")
        if isinstance(ships, bool) or not isinstance(ships, (int, float)):
            raise ActionFormatError("ships must be a positive integer")
        if not math.isfinite(ships) or not float(ships).is_integer():
            raise ActionFormatError("ships must be a positive integer")
        return cls(from_planet_id=int(from_planet_id), angle=float(angle), ships=int(ships))


def decode_raw_action(value: object) -> list[LaunchCommand]:
    """Convert one player's original action list into validated commands."""

    if not isinstance(value, (list, tuple)):
        raise ActionFormatError("an action must be a list of launch commands")
    return [LaunchCommand.from_raw(item) for item in value]


def encode_action(commands: list[LaunchCommand]) -> RawAction:
    """Convert validated commands back to the original engine action shape."""

    return [command.to_raw() for command in commands]
