"""4P (FFA) strategy hooks.

Strategy differences between 2P and 4P live here and in ``strategy_2p.py``;
``main.py`` imports the right one based on player_count. Each file exposes the
same set of hook functions with identical signatures.

4P specifics implemented here:
- Keeps the BASELINE behaviour (no v1 early-aggression). The v1 ROI-lowering
  trick measurably degrades 4P (v0 38% → v1 15% on the local pool). 4P needs
  conservative play because being attacked from two sides at once is the main
  failure mode — bleeding ships into low-ROI early launches makes it worse.

Future 4P improvements (suppress leader, avoid king-making, etc.) belong here.
"""
from __future__ import annotations


def effective_roi_threshold(*, config, cur_step: int) -> float:
    """ROI gate for the greedy wave selector at the current turn.

    [v50] 4P roi=1.0: v49 修了 nearer_sum padding bug (合击兵力不再虚增) 后, score 更可信,
    不需要 v48 的 1.2 高门槛来"补偿虚增". 降到 1.0 (只要确信正收益就打), 在 nearer_sum
    修复基础上恢复一点进攻性, 看 4P 是否更好. env PRODUCER_ROI_THRESHOLD 仍可覆盖.
    """
    import os
    _ov = os.environ.get("PRODUCER_ROI_THRESHOLD")
    if _ov is not None:
        return float(_ov)
    return 1.0
