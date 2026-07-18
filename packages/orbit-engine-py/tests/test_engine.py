from __future__ import annotations

import math

import pytest
from orbit_engine import (
    DEFAULT_RULESET_REGISTRY,
    PINNED_CONFIG,
    PINNED_RULESET_ID,
    ActionFormatError,
    LaunchCommand,
    OrbitEngine,
    RulesetConfig,
    UnknownRulesetError,
    decode_raw_action,
    encode_action,
)


def test_fixed_seed_reset_is_deterministic_and_seed_is_not_in_snapshot() -> None:
    first = OrbitEngine()
    second = OrbitEngine()

    first_snapshot = first.reset(seed=1_234_567)
    second_snapshot = second.reset(seed=1_234_567)

    assert first_snapshot == second_snapshot
    assert first_snapshot.ruleset_id == PINNED_RULESET_ID
    assert first_snapshot.config == PINNED_CONFIG
    assert first_snapshot.step == 0
    assert first_snapshot.state_hash == (
        "9d67c5256d8cc7acca35c79fee4b78c0bf508d6d698b716eb99057475f7855f4"
    )
    assert not hasattr(first_snapshot, "seed")
    assert first.seed == 1_234_567


def test_player_snapshots_share_authoritative_hash_without_seed_disclosure() -> None:
    engine = OrbitEngine()
    engine.reset(seed=42)

    player_zero = engine.snapshot(player=0)
    player_one = engine.snapshot(player=1)

    assert player_zero.player == 0
    assert player_one.player == 1
    assert player_zero.state_hash == player_one.state_hash
    assert player_zero.seed_commitment == player_one.seed_commitment
    assert str(engine.seed) not in player_zero.seed_commitment


def test_legacy_action_round_trip_preserves_angle_and_values() -> None:
    raw = [[3, -math.pi / 7, 11], [8, 9.25, 2]]

    commands = decode_raw_action(raw)

    assert encode_action(commands) == raw
    assert commands[0] == LaunchCommand(from_planet_id=3, angle=-math.pi / 7, ships=11)


def test_legacy_action_canonicalizes_integral_json_floats() -> None:
    assert encode_action(decode_raw_action([[15.0, 2.5, 25.0]])) == [[15, 2.5, 25]]


@pytest.mark.parametrize(
    "raw",
    [
        [[1, math.nan, 2]],
        [[1, math.inf, 2]],
        [[True, 0.0, 2]],
        [[1, 0.0, True]],
        [[1, 0.0, 0]],
        [[1.5, 0.0, 2]],
        [[1, 0.0, 2.5]],
        [[1, 0.0]],
        "not-an-action",
    ],
)
def test_legacy_action_adapter_rejects_invalid_values(raw: object) -> None:
    with pytest.raises(ActionFormatError):
        decode_raw_action(raw)


def test_step_raw_launches_for_both_players_and_advances_once() -> None:
    engine = OrbitEngine()
    initial = engine.reset(seed=1_234_567)
    homes = {planet.owner: planet for planet in initial.planets if planet.owner in (0, 1)}

    result = engine.step_raw(
        [
            [[homes[0].id, 0.0, 5]],
            [[homes[1].id, math.pi, 5]],
        ]
    )

    assert result.snapshot.step == 1
    assert not result.done
    assert result.rewards == (0, 0)
    assert {
        (fleet.owner, fleet.from_planet_id, fleet.ships) for fleet in result.snapshot.fleets
    } == {
        (0, homes[0].id, 5),
        (1, homes[1].id, 5),
    }
    updated = {planet.id: planet for planet in result.snapshot.planets}
    assert updated[homes[0].id].ships == 5 + homes[0].production
    assert updated[homes[1].id].ships == 5 + homes[1].production
    assert result.snapshot.state_hash == (
        "576affa4fbd720fb85d003b5abb7973fcb9b8d2bde081884f2bcda9eb22913b2"
    )


def test_ruleset_configuration_and_registry_are_immutable() -> None:
    assert DEFAULT_RULESET_REGISTRY.ids() == (PINNED_RULESET_ID,)
    assert DEFAULT_RULESET_REGISTRY.create(PINNED_RULESET_ID).config == PINNED_CONFIG

    with pytest.raises(ValueError, match="immutable configuration"):
        OrbitEngine(RulesetConfig(episode_steps=50))
    with pytest.raises(UnknownRulesetError):
        DEFAULT_RULESET_REGISTRY.create("orbit-wars-2p-v2")


def test_ruleset_rejects_non_two_player_reset() -> None:
    with pytest.raises(ValueError, match="exactly two players"):
        OrbitEngine().reset(seed=7, players=4)
