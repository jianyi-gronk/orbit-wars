"""Deterministic events, metric curves, and factual outcome summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BattleEvent:
    type: str
    step: int
    slot: int | None
    detail: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {"type": self.type, "step": self.step, "slot": self.slot, **self.detail}


@dataclass(frozen=True, slots=True)
class ReplayAnalysis:
    events: tuple[BattleEvent, ...]
    metrics: tuple[dict[str, Any], ...]
    victory_facts: tuple[str, ...]


def reconstruct_frames(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for record in records:
        if record.get("type") == "checkpoint":
            current = dict(record["frame"])
        elif record.get("type") == "delta" and current is not None:
            current = {**current, **record["frame"]}
        else:
            continue
        frames.append({**current, "commands": record.get("commands", [[], []])})
    return frames


def analyze_records(records: list[dict[str, Any]]) -> ReplayAnalysis:
    frames = reconstruct_frames(records)
    if not frames:
        return ReplayAnalysis((), (), ())
    events: list[BattleEvent] = []
    metrics: list[dict[str, Any]] = []
    initial = frames[0]
    home_planets = {slot: _home_planet(initial.get("planets", []), slot) for slot in (0, 1)}
    previous_owners = {int(row[0]): int(row[1]) for row in initial.get("planets", [])}
    previous_production_leader: int | None = None
    previous_ship_leader: int | None = None
    eliminated: set[int] = set()
    largest_launch = 0

    for frame in frames:
        step = int(frame["step"])
        planets = frame.get("planets", [])
        fleets = frame.get("fleets", [])
        current_owners = {int(row[0]): int(row[1]) for row in planets}
        for planet_id, owner in current_owners.items():
            previous = previous_owners.get(planet_id, -1)
            if owner in (0, 1) and owner != previous:
                events.append(
                    BattleEvent(
                        "planet_captured",
                        step,
                        owner,
                        {"planetId": planet_id, "previousOwner": previous},
                    )
                )
            for slot, home_id in home_planets.items():
                if planet_id == home_id and previous == slot and owner != slot:
                    events.append(
                        BattleEvent("home_planet_lost", step, slot, {"planetId": planet_id})
                    )
        previous_owners = current_owners

        for slot, commands in enumerate(frame.get("commands", [[], []])):
            for command in commands:
                ships = int(command[2])
                if ships > largest_launch:
                    largest_launch = ships
                    events.append(
                        BattleEvent(
                            "largest_launch",
                            step,
                            slot,
                            {"ships": ships, "fromPlanetId": int(command[0])},
                        )
                    )

        player_metrics = [_metrics(planets, fleets, slot) for slot in (0, 1)]
        production_leader = _leader(
            player_metrics[0]["production"], player_metrics[1]["production"]
        )
        ship_leader = _leader(
            player_metrics[0]["stationedShips"] + player_metrics[0]["inTransitShips"],
            player_metrics[1]["stationedShips"] + player_metrics[1]["inTransitShips"],
        )
        if (
            production_leader != previous_production_leader
            and previous_production_leader is not None
        ):
            events.append(
                BattleEvent(
                    "production_lead_changed",
                    step,
                    production_leader,
                    {"leader": production_leader},
                )
            )
        if ship_leader != previous_ship_leader and previous_ship_leader is not None:
            events.append(
                BattleEvent("ship_lead_changed", step, ship_leader, {"leader": ship_leader})
            )
        previous_production_leader = production_leader
        previous_ship_leader = ship_leader
        for slot in (0, 1):
            if (
                slot not in eliminated
                and player_metrics[slot]["planets"] == 0
                and player_metrics[slot]["inTransitShips"] == 0
            ):
                eliminated.add(slot)
                events.append(BattleEvent("player_eliminated", step, slot, {}))
        metrics.append({"step": step, "players": player_metrics})

    result: dict[str, Any] = next(
        (record.get("result", {}) for record in records if record.get("type") == "result"),
        {},
    )
    final_step = int(result.get("finalStep", frames[-1]["step"]))
    reason = str(result.get("reason", "unknown"))
    if reason in {"agent_timeout", "human_disconnect"}:
        events.append(BattleEvent(reason, final_step, result.get("loserSlot"), {"reason": reason}))
    events.append(
        BattleEvent(
            "match_finished",
            final_step,
            result.get("winnerSlot"),
            {"reason": reason},
        )
    )
    return ReplayAnalysis(
        events=tuple(events),
        metrics=tuple(metrics),
        victory_facts=_victory_facts(result, metrics, events),
    )


def _home_planet(planets: list[list[int | float]], slot: int) -> int | None:
    owned = [row for row in planets if int(row[1]) == slot]
    return int(max(owned, key=lambda row: float(row[5]))[0]) if owned else None


def _metrics(
    planets: list[list[int | float]], fleets: list[list[int | float]], slot: int
) -> dict[str, int | float]:
    owned = [row for row in planets if int(row[1]) == slot]
    in_transit = [row for row in fleets if int(row[1]) == slot]
    total_planets = max(1, len(planets))
    return {
        "planets": len(owned),
        "production": sum(float(row[6]) for row in owned),
        "stationedShips": sum(float(row[5]) for row in owned),
        "inTransitShips": sum(float(row[6]) for row in in_transit),
        "controlRate": len(owned) / total_planets,
    }


def _leader(first: float, second: float) -> int | None:
    if first == second:
        return None
    return 0 if first > second else 1


def _victory_facts(
    result: dict[str, Any],
    metrics: list[dict[str, Any]],
    events: list[BattleEvent],
) -> tuple[str, ...]:
    winner = result.get("winnerSlot")
    if winner not in (0, 1) or not metrics:
        return (f"比赛以 {result.get('reason', 'unknown')} 结束，未产生唯一胜者。",)
    final = metrics[-1]["players"][winner]
    final_planets = final["planets"]
    control_rate = final["controlRate"]
    final_production = final["production"]
    final_ships = final["stationedShips"] + final["inTransitShips"]
    facts = [
        f"胜方槽位 {winner} 最终控制 {final_planets} 颗星球，控制率 {control_rate:.0%}。",
        f"胜方最终产能 {final_production:.0f}，驻守与在途兵力合计 {final_ships:.0f}。",
    ]
    captures = sum(
        1 for event in events if event.type == "planet_captured" and event.slot == winner
    )
    facts.append(f"胜方在权威帧中完成 {captures} 次占领。")
    return tuple(facts)
