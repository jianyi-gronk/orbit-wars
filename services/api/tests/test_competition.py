from orbit_api.domain.competition import battle_intensity, competition_record, select_highlights


def test_competition_record_is_draw_aware_and_sample_protected() -> None:
    record = competition_record(
        [
            (0, {"winnerSlot": 0}),
            (0, {"winnerSlot": 1}),
            (0, {"winnerSlot": None}),
        ]
    )
    empty = competition_record([])

    assert record == {
        "matches": 3,
        "wins": 1,
        "losses": 1,
        "draws": 1,
        "winRate": 1 / 3,
        "adjustedWinRate": 2 / 5,
    }
    assert empty == {
        "matches": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "winRate": 0.0,
        "adjustedWinRate": 0.5,
    }
    assert competition_record([(0, {"winnerSlot": 0})])["adjustedWinRate"] == 2 / 3
    assert competition_record([(0, {"winnerSlot": 0})] * 8 + [(0, {"winnerSlot": 1})] * 2)[
        "adjustedWinRate"
    ] == 9 / 12


def test_battle_intensity_is_deterministic_bounded_and_handles_missing_analysis() -> None:
    analysis = {
        "events": [
            {"type": "planet_captured", "step": 20},
            {"type": "planet_captured", "step": 35},
            {"type": "ship_lead_changed", "step": 50},
            {"type": "production_lead_changed", "step": 72},
            {"type": "largest_launch", "step": 91},
            {"type": "home_planet_lost", "step": 140},
        ]
    }
    first = battle_intensity(analysis, 168, [{"delta": 42}, {"delta": -42}])
    second = battle_intensity(analysis, 168, [{"delta": 42}, {"delta": -42}])

    assert first == second
    assert 0 <= first["score"] <= 100
    assert first["featured"] is True
    assert first["band"] in {"routine", "contested", "volatile"}
    assert battle_intensity(None, 0, [None]) == {
        "score": 0,
        "band": "routine",
        "signals": [],
        "featured": False,
    }


def test_highlights_are_semantic_limited_and_chronological() -> None:
    highlights = select_highlights(
        {
            "events": [
                {"type": "match_finished", "step": 168},
                {"type": "planet_captured", "step": 22},
                {"type": "home_planet_lost", "step": 150},
                {"type": "ship_lead_changed", "step": 70},
                {"type": "largest_launch", "step": 70},
                {"type": "ignored", "step": 5},
            ]
        }
    )

    assert len(highlights) == 3
    assert [event["step"] for event in highlights] == [22, 70, 150]
    assert [event["type"] for event in highlights] == [
        "planet_captured",
        "ship_lead_changed",
        "home_planet_lost",
    ]
    assert select_highlights(None) == []
    assert select_highlights({"events": []}, limit=0) == []
