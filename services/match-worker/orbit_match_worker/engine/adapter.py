"""Match Worker boundary around the versioned engine registry."""

from __future__ import annotations

from orbit_engine import (
    DEFAULT_RULESET_REGISTRY,
    EngineSnapshot,
    EngineStepResult,
    LaunchCommand,
    RulesetRegistry,
)


class EngineAdapter:
    def __init__(
        self,
        ruleset_id: str,
        *,
        registry: RulesetRegistry = DEFAULT_RULESET_REGISTRY,
    ) -> None:
        self.ruleset_id = ruleset_id
        self._engine = registry.create(ruleset_id)

    @property
    def done(self) -> bool:
        return self._engine.done

    def reset(self, *, seed: int, slots: tuple[int, int]) -> EngineSnapshot:
        if slots != (0, 1):
            raise ValueError("the pinned 2P ruleset requires slots (0, 1)")
        return self._engine.reset(seed=seed, players=2)

    def snapshot(self, *, player: int | None = None) -> EngineSnapshot:
        return self._engine.snapshot(player=player)

    def step(self, actions: list[list[LaunchCommand]]) -> EngineStepResult:
        return self._engine.step(actions)
