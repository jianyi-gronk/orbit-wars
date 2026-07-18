"""2P (head-to-head) strategy hooks.

Strategy differences between 2P and 4P live in this file and ``strategy_4p.py``;
``main.py`` imports the right one based on player_count. Each file exposes the
same set of hook functions with identical signatures.

2P specifics implemented here:
- Early-game aggressive ROI threshold (v1 fix for seed6/slot0 do-nothing opening).
  Validated +10pp 2P win-rate (85→95). DOES NOT WORK in 4P (drops 4P 38→15) —
  hence isolated to this 2P file. See strategy_4p.py for the 4P version.
"""
from __future__ import annotations


def effective_roi_threshold(*, config, cur_step: int) -> float:
    """ROI gate for the greedy wave selector at the current turn.

    2P: lower the gate to ``early_roi_threshold`` for the first
    ``early_aggression_turns`` turns, so we don't sit idle on maps where every
    nearby neutral scores just under 1.5 (seed6/slot0 collapse).
    """
    base = float(config.roi_threshold)
    if config.early_aggression_turns > 0 and cur_step < int(config.early_aggression_turns):
        return min(base, float(config.early_roi_threshold))
    return base
