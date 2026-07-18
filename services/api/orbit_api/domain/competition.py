"""Pure competition facts shared by public ranking and match summaries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

FEATURED_INTENSITY_THRESHOLD = 60


def competition_record(
    results: Iterable[tuple[int, Mapping[str, Any] | None]],
) -> dict[str, int | float]:
    """Return a draw-aware record with a Beta(1, 1) sample-protected win rate."""

    matches = wins = losses = draws = 0
    for slot, result in results:
        matches += 1
        winner = result.get("winnerSlot") if result else None
        if winner == slot:
            wins += 1
        elif winner in (0, 1):
            losses += 1
        else:
            draws += 1
    return {
        "matches": matches,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "winRate": wins / matches if matches else 0.0,
        "adjustedWinRate": (wins + 1) / (matches + 2),
    }


def battle_intensity(
    analysis: Mapping[str, Any] | None,
    frame_count: int,
    rating_changes: Sequence[Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Build a deterministic, bounded audience-facing battle intensity score."""

    events = analysis.get("events", []) if analysis else []
    event_types = [event.get("type") for event in events if isinstance(event, Mapping)]
    captures = event_types.count("planet_captured")
    lead_changes = event_types.count("production_lead_changed") + event_types.count(
        "ship_lead_changed"
    )
    decisive_events = event_types.count("home_planet_lost") + event_types.count(
        "player_eliminated"
    )
    has_largest_launch = "largest_launch" in event_types
    max_rating_delta = max(
        (
            abs(float(change.get("delta", 0)))
            for change in rating_changes
            if isinstance(change, Mapping)
        ),
        default=0.0,
    )

    score = min(20, round(max(frame_count, 0) / 8))
    score += min(24, captures * 2)
    score += min(24, lead_changes * 6)
    score += min(16, decisive_events * 8)
    score += min(16, round(max_rating_delta * 0.3))
    score += 4 if has_largest_launch else 0
    score = min(100, score)

    signals: list[str] = []
    if frame_count >= 120:
        signals.append("long_battle")
    if captures:
        signals.append("planet_swings")
    if lead_changes:
        signals.append("lead_changes")
    if decisive_events:
        signals.append("decisive_finish")
    if max_rating_delta >= 25:
        signals.append("rating_swing")
    if has_largest_launch:
        signals.append("largest_launch")

    band = "volatile" if score >= 70 else "contested" if score >= 40 else "routine"
    return {
        "score": score,
        "band": band,
        "signals": signals,
        "featured": score >= FEATURED_INTENSITY_THRESHOLD,
    }


def select_highlights(
    analysis: Mapping[str, Any] | None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Select a small, deterministic and chronologically ordered highlight reel."""

    if limit <= 0 or not analysis:
        return []
    events = analysis.get("events", [])
    priorities = {
        "home_planet_lost": 100,
        "player_eliminated": 95,
        "production_lead_changed": 80,
        "ship_lead_changed": 80,
        "planet_captured": 65,
        "largest_launch": 55,
        "match_finished": 40,
    }
    candidates = [
        dict(event)
        for event in events
        if isinstance(event, Mapping) and event.get("type") in priorities
    ]
    candidates.sort(
        key=lambda event: (
            -priorities[str(event["type"])],
            int(event.get("step", 0)),
            str(event["type"]),
        )
    )
    selected: list[dict[str, Any]] = []
    selected_steps: set[int] = set()
    for event in candidates:
        step = int(event.get("step", 0))
        if step in selected_steps:
            continue
        selected.append(event)
        selected_steps.add(step)
        if len(selected) == limit:
            break
    return sorted(selected, key=lambda event: int(event.get("step", 0)))
