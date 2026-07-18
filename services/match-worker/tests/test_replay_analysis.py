from copy import deepcopy

from orbit_match_worker.replay.analysis import analyze_records


def frame(step, planets, fleets=None, commands=None, *, checkpoint=False):
    return {
        "type": "checkpoint" if checkpoint else "delta",
        "frame": {
            "step": step,
            "stateHash": str(step),
            "planets": planets,
            "fleets": fleets or [],
            "rewards": [0, 0],
        },
        "commands": commands or [[], []],
    }


def test_event_metrics_and_victory_facts_are_stably_derived_without_mutating_frames() -> None:
    initial = [[0, 0, 0, 0, 2, 20, 2], [1, 1, 10, 10, 2, 20, 2], [2, -1, 5, 5, 1, 5, 1]]
    captured = [[0, 0, 0, 0, 2, 10, 2], [1, 1, 10, 10, 2, 12, 2], [2, 0, 5, 5, 1, 8, 1]]
    home_lost = [[0, 1, 0, 0, 2, 4, 2], [1, 1, 10, 10, 2, 14, 2], [2, 0, 5, 5, 1, 9, 1]]
    eliminated = [[0, 1, 0, 0, 2, 4, 2], [1, 1, 10, 10, 2, 14, 2], [2, 1, 5, 5, 1, 9, 1]]
    records = [
        frame(0, initial, checkpoint=True),
        frame(1, captured, commands=[[[0, 1.0, 9]], []]),
        frame(2, home_lost, commands=[[], [[1, 2.0, 12]]]),
        frame(3, eliminated),
        {"type": "result", "result": {"winnerSlot": 1, "reason": "elimination", "finalStep": 3}},
    ]
    source = deepcopy(records)
    first = analyze_records(records)
    second = analyze_records(records)
    event_types = {event.type for event in first.events}

    assert records == source
    assert first == second
    assert {
        "planet_captured",
        "home_planet_lost",
        "largest_launch",
        "production_lead_changed",
        "ship_lead_changed",
        "player_eliminated",
        "match_finished",
    }.issubset(event_types)
    assert len(first.metrics) == 4
    assert first.metrics[-1]["players"][1]["controlRate"] == 1
    assert all("胜方" in fact for fact in first.victory_facts)
