"""Explicit registry for immutable Orbit Wars rulesets."""

from __future__ import annotations

from collections.abc import Callable

from orbit_engine.engine import PINNED_RULESET_ID, OrbitEngine

OrbitEngineFactory = Callable[[], OrbitEngine]


class UnknownRulesetError(KeyError):
    pass


class RulesetRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, OrbitEngineFactory] = {}

    def register(self, ruleset_id: str, factory: OrbitEngineFactory) -> None:
        if ruleset_id in self._factories:
            raise ValueError(f"ruleset {ruleset_id!r} is already registered")
        self._factories[ruleset_id] = factory

    def get(self, ruleset_id: str) -> OrbitEngineFactory:
        try:
            return self._factories[ruleset_id]
        except KeyError as exc:
            raise UnknownRulesetError(ruleset_id) from exc

    def create(self, ruleset_id: str) -> OrbitEngine:
        return self.get(ruleset_id)()

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


DEFAULT_RULESET_REGISTRY = RulesetRegistry()
DEFAULT_RULESET_REGISTRY.register(PINNED_RULESET_ID, OrbitEngine)
