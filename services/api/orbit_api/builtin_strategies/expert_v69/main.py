
from __future__ import annotations

import dataclasses
import os
import sys
from dataclasses import dataclass

# [v47 = v46 + 前线源星禁打中立约束]
#   - 继承 v46: obs.step=None 修复 + max suppression
#   - 用户洞察 replay 80046504 t27: P1 派 30 兵 from p31 打 p18 (中立), 但 71 兵敌方反扑
#     正在飞向 p31. 即使 obs.step bug 修复后 score 公式看到威胁, 仍可能因别的原因派兵.
#     v47 加策略层兜底: 源星 k=6 内有敌方 fleet 在途 → 禁止派该源打中立 (前线急需守).
#   - 仅禁中立, 不禁打敌方 (用户:"敌方腹地守不住时打敌方小星削收益是合理的"). 也不禁
#     regroup (友方 muster 集结). env PRODUCER_NO_FRONTLINE_NEUTRAL_BAN 关闭.
# [v46 旧注释保留:]
# [v46 = v45 + 修 obs.step=None bug (P1/P2/P3 视角 movement 投影错位)]
#   - 继承 v45: max(星数,兵力) suppression
#   - 关键 bug 修复: kaggle_environments 实测 P0 obs.step 有效, 但 P1/P2/P3 obs.step=None.
#     adapter 默认 fallback 到 0 → movement 用 step=0 算 orbit phase → 旋转星位置全错
#     → swept_collides 误判 fleet 撞错星 → fleet_buckets 漏记关键反扑.
#     replay 80046504 t27 (Gronk=P1): 71 兵 fleet 飞 p31 没进 fleet_buckets → score 看不
#     到反扑 → 派 30 兵 from p31 打 p18 中立 → t32 p31 被夺.
#     Gronk 24 局 LB 输局中 80% 是 P1/P2/P3 位置 — 这是核心 bug.
#   - 修法: agent 入口检查 obs.step, None 时用 module-level counter 累加 fallback.
# [v45 旧注释保留: suppression scale 用 max(星数, 兵力) share]
#   - 继承 v44: 双向 muster, arr 迭代, capture_floor pre_combat, hold(x) 自产从 eta 起算
#   - 修 4P suppression scale 单一维度滞后 bug: scale = 1 - max(星数 share, 兵力 share).
#     取 max 兼顾两类主敌:
#     • 攒兵突袭型 (兵力 share 高 — 4 颗大星囤 288 兵 share=0.66)
#     • 稳定雪球型 (星数 share 高 — 15 颗小星稳定占据 share=0.6)
#     任一维度领先都触发压制. 旧版纯星数算 P1 t44 share=0.44 → scale=0.56 (仍计 56% 战损 →
#     不敢打); 新版 max(0.44, 0.66)=0.66 → scale=0.34 (更敢压制攒兵主敌).
#   - 注: H/INIT/SAT 修法尝试过但 4P/2P 双退化 (派太多兵打远距打不下 → 本地空虚被反扑), 撤回.
#   - env PRODUCER_SUPPRESS_BY_STARS=1 / BY_SHIPS=1 回退单一维度版本.
# env: PRODUCER_NO_ROT_STAT_SPLIT 关闭。
os.environ.setdefault("PRODUCER_PRESSURE_PROPAGATE", "1")
os.environ.setdefault("PRODUCER_EARLY_DELAY_BOOST", "1")

# Make the sibling ``orbit_lite`` package importable wherever this file runs:
# loaded in place, dropped at a submission-archive root, or exec'd by
# kaggle_environments with no ``__file__`` (fall back to the working dir).
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.getcwd()
if _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, _HERE)
for _mod_name in [
    m for m in sys.modules
    if m in ("strategy_2p", "strategy_4p") or m == "orbit_lite" or m.startswith("orbit_lite.")
]:
    del sys.modules[_mod_name]

import torch
from torch import Tensor

from orbit_lite.movement import MovementConfig, PlanetMovement
from orbit_lite.movement_step import (
    LaunchEntries,
    apply_private_planned_launches,
    concat_launch_entries,
    disambiguate_duplicate_launches,
    ensure_planet_movement,
    infer_planned_launches_from_entries,
)
from orbit_lite.obs import parse_obs
from orbit_lite.distance_cache import build_distance_cache
from orbit_lite.planner_core import (
    _candidate_indices,
    _empty_entries,
    _plan_regroup,
    plan_iterative_waves,
    reachable_mass,
    build_attack_candidates,
    build_target_shortlist,
    capture_floor,
    enemy_reinforcement_schedule,
    friendly_reinforcement_schedule,
    empty_action_row,
    entries_to_sparse_payload,
    largest_initial_player_count,
    make_launch_set,
    safe_drain,
    score_candidates,
    split_player_same_step_net,
)
from orbit_lite.adapter import single_obs_to_tensor, sparse_action_row_to_moves
from orbit_lite.geometry import fleet_speed
from orbit_lite.intercept_aim import intercept_angle
from orbit_lite.movement_aiming import LAUNCH_SURFACE_OFFSET, TARGET_HIT_SURFACE_OFFSET

# Player-count-specific strategy hooks: 2P/4P branches live in sibling files so
# 2P-only fixes (e.g. v1's early-aggression) don't bleed into 4P. main.py picks
# the right module per turn via `player_count`. Each hook module exposes the
# same function signatures.
import strategy_2p as _strat_2p
import strategy_4p as _strat_4p
# Keep the bound module objects above, but do not leave generic strategy module
# names behind for another submission loaded later in the same interpreter.
sys.modules.pop("strategy_2p", None)
sys.modules.pop("strategy_4p", None)

# [v62 = v62-4p + low static-count pending hold]
#   - Global pending hold saved low seeds 32/2078/2957 but lost rotating-heavy
#     seeds 1843/2412/2663/7314. The saved seeds share a static-rich initial
#     layout. Enable pending hold only on low-production 4P maps with at least
#     16 non-comet static planets.
# [v62-4p = v61 + low rotating neutral-ban release]
#   - Low-production rotating-dominant maps: release the frontline-neutral ban
#     only when rotating production dominates and the biggest production planet is
#     rotating. This is the previously clean local-panel signal.
# [v61 = v60 + promoted 2P late-defense decay and big-long-uncertain penalty]
#   - Keep current v60's 4P race-bucket base.
#   - Add the best 2P panel improvement: after t50, late own-planet
#     "defenses" and large long low-hold-confidence commitments are score-decayed.
# [v60 = v60-4p-29 promoted: stable initial-map-production race buckets]
# v58 replaced the ROI ranking key with a pure production-share race value. Local
# panel showed it could lift t50 share but hurt t80 share/rank, so v59 keeps v53's
# score/cost ranking and adds only a small positive race bonus:
#   rank_value = score + PRODUCER_RACE_WEIGHT * max(0, race_value)
# score remains the feasibility/gate. Enabled only while current 4P are all alive
# and t < PRODUCER_RACE_END(default 80). 128-panel bucket reruns showed different
# race timing by map production: high and med-low maps prefer no race nudge before
# t30, med-high maps prefer pre-t50 neutral-only race, and low maps prefer the v59
# default. Buckets use initial_planets total production, not current live production,
# so expansion/comet state cannot move the map between buckets mid-game.
# Env: PRODUCER_NO_RACE_ROI disables.

@dataclass(frozen=True)
class ProducerLiteConfig:
    """Behaviour knobs.  """


    # the projection window, the movement build length, AND the target ETA cap.
    # [v26] LOCKED at 18. H=30 makes single-wave occupation-hold PREDICTION more accurate
    # (hold比值 0.77→0.97) BUT collapses win rate (clean arena vs v20: H18 60% / H21 50% /
    # H30 18.8%, monotone). Root cause = horizon enlarges produced's absolute magnitude
    # uniformly → scrambles the RELATIVE ranking of candidates, and greedy decisions only
    # see ranking (ledger's iron law: produced-magnitude scaling breaks the champion's
    # co-calibrated ranking; outcome depends only on order). The accurate-prediction goal
    # conflicts with the ranking-optimal decision; H=18 is the ranking-optimal point.
    horizon: int = 18
    # --- shortlists ------------------------------------------------------
    max_sources_per_lane: int = 12
    max_offensive_targets: int = 12         # enemy/neutral proximity targets
    max_defensive_targets: int = 4
    # --- scoring / greedy ------------------------------------------------
    max_waves_per_turn: int = 6
    # [v26] ROI gate = net competitive value > 0. The old 1.5 was a margin to compensate
    # for over-valued occupation (produced assumed hold-to-horizon, capture-floor used a
    # noisy reinforcement proxy). Now occupation value is computed from the engine-exact
    # ballistic hold(x) and a post-combat capture floor — a positive net score IS a real
    # expected gain, so fire whenever it clears 0.
    roi_threshold: float = 0.0              # fire if net score > 0
    # [v1] early aggression now coincides with the base gate (both 0); kept for the knob.
    early_aggression_turns: int = 20
    early_roi_threshold: float = 0.0
    min_ships_to_launch: float = 4.0
    # --- regroup  ------------------------------
    enable_regroup: bool = True
    max_regroup_time: float = 7.0
    regroup_pressure_delta_min: float = 0.25
    max_regroup_sources_per_lane: int = 6
    max_regroup_targets_per_source: int = 7
    regroup_pressure_norm: str = "none"
    regroup_time_penalty_weight: float = 1e-3


_DELAY_MAX = 6  # [v37] 5→6: 加一档 d=6 让早期"等 6 回合攒兵打大星"成为正式候选


def _movement_config(config: ProducerLiteConfig, *, player_count: int) -> MovementConfig:
    """MovementConfig: fleet tracking on, horizon = config.horizon. Delayed-launch
    aim reads step-d positions within this same cache (launch_turn + flight is kept
    within the horizon), so no extra depth is needed."""
    return MovementConfig(
        movement_horizon=int(config.horizon),
        drift_epsilon=1e-3,
        track_fleets=True,
        player_count=int(player_count),
        max_tracked_fleets=128,
    )


# [v25] Reachable-mass proxy moved to the framework (planner_core.reachable_mass) —
# pure mechanism. This thin shim keeps the historical name the regroup gradient uses.
def cheap_enemy_pressure(obs, cache, *, horizon: float, player_id: int) -> Tensor:
    return reachable_mass(obs, cache, horizon=horizon, player_id=player_id, side="enemy")


def _rotating_reserve_multiplier(obs, cache, *, reserve_full_P, pid, K_eta, device, dtype) -> Tensor:
    """Per-planet multiplier for rotating-planet defensive reserve.

    v67's default treats rotating friendly planets as attack bases and gives them
    no min_keep reserve. That is correct for isolated rotators that drift into the
    enemy side, but not for a rotating planet that is still inside our supported
    front. Restore reserve only for supported, non-overmatched rotators; keep the
    old 0-reserve behavior for isolated/deep rotators.
    """
    P = int(obs.P)
    base_mult = float(os.environ.get("PRODUCER_ROT_RESERVE_MULT", "0.0"))
    mult = torch.full((P,), base_mult, dtype=dtype, device=device)
    rot_owned = obs.owned & obs.alive & obs.is_orbiting
    if not bool(rot_owned.any()):
        return mult

    rot_h = float(os.environ.get("PRODUCER_ROT_ISOLATED_H", str(K_eta)))
    ships = obs.ships.to(dtype)
    if os.environ.get("PRODUCER_ROT_SUPPORTED_CURRENT_NEAR", "1") == "1":
        d_support = cache.cross_dist[0].to(dtype)                                # [src, tgt], current frame
    else:
        K = max(1, min(int(rot_h), int(cache.cross_dist.shape[0]) - 1))
        d_support = cache.cross_dist[1 : K + 1].to(dtype).amin(dim=0)             # [src, tgt], future min
    surface_gap = (
        obs.r.to(dtype).view(P, 1)
        + float(LAUNCH_SURFACE_OFFSET)
        + obs.r.to(dtype).view(1, P)
        + float(TARGET_HIT_SURFACE_OFFSET)
    )
    d_support = (d_support - surface_gap).clamp(min=0.0)
    reach_dist = (fleet_speed(ships.clamp(min=1e-6)).to(dtype).view(P, 1) * rot_h).clamp(min=1e-6)
    decay = (1.0 - d_support / reach_dist).clamp(min=0.0)
    eye = torch.eye(P, dtype=torch.bool, device=device)
    friend_src = obs.alive & (obs.owner_abs == int(pid))
    enemy_src = obs.alive & (obs.owner_abs >= 0) & (obs.owner_abs != int(pid))
    valid_tgt = obs.alive.view(1, P) & ~eye
    friend_mass = torch.where(
        friend_src.view(P, 1) & valid_tgt,
        ships.view(P, 1) * decay,
        torch.zeros_like(decay),
    ).sum(dim=0)
    enemy_mass = torch.where(
        enemy_src.view(P, 1) & valid_tgt,
        ships.view(P, 1) * decay,
        torch.zeros_like(decay),
    ).sum(dim=0)
    weak_support = friend_mass <= (
        ships * float(os.environ.get("PRODUCER_ROT_ISOLATED_FRIEND_RATIO", "0.35"))
        + float(os.environ.get("PRODUCER_ROT_ISOLATED_FRIEND_MARGIN", "4.0"))
    )
    enemy_overmatch = enemy_mass >= (
        ships * float(os.environ.get("PRODUCER_ROT_ISOLATED_ENEMY_RATIO", "1.0"))
        + friend_mass
        + float(os.environ.get("PRODUCER_ROT_ISOLATED_ENEMY_MARGIN", "8.0"))
    )

    if os.environ.get("PRODUCER_ROT_SUPPORTED_RESERVE"):
        need = reserve_full_P.to(device=device, dtype=dtype)
        has_need = need >= float(os.environ.get("PRODUCER_ROT_SUPPORTED_MIN_KEEP", "1.0"))
        friend_side = friend_mass >= (
            enemy_mass * float(os.environ.get("PRODUCER_ROT_SUPPORTED_FRIEND_ENEMY_RATIO", "1.0"))
            + float(os.environ.get("PRODUCER_ROT_SUPPORTED_FRIEND_ENEMY_MARGIN", "0.0"))
        )
        supported_rot = rot_owned & has_need & (~weak_support) & (~enemy_overmatch) & friend_side
        mult = torch.where(
            supported_rot,
            torch.full_like(mult, float(os.environ.get("PRODUCER_ROT_SUPPORTED_RESERVE_MULT", "1.0"))),
            mult,
        )

    if not os.environ.get("PRODUCER_NO_ROT_ISOLATED_RELEASE"):
        isolated_rot = rot_owned & weak_support & enemy_overmatch
        mult = torch.where(
            isolated_rot,
            torch.full_like(mult, float(os.environ.get("PRODUCER_ROT_ISOLATED_RESERVE_MULT", "0.0"))),
            mult,
        )
    return mult


def _compute_min_keep(obs, cache, *, source_idx, prod, k, device, dtype, garrison_status=None, movement=None):
    """[v33] 每颗源星的最小留守兵 min_keep — 对称k窗口攻防(用户安全兵力公式)。

    可达性: 星s能k回合到星t ⟺ fleet_speed(s兵)·k ≥ cross_dist[k,s,t](源@0→目标@k)。
    敌/友k可达 **= 星上兵(可达) + 在途舰队(arrivals_by_owner, 精确弹道k回合到t)** (用户: 必须算在途)。
    对每颗我方星 X 算 守自己缺口 self_gap(X)=max(0, 敌k可达X − 友方k可达X(不含X自身))。
    A 帮邻星 B 的缺口 = max(0, 敌k可达B − (友方k可达B − A对B的贡献))。
    min_keep(A) = max(self_gap(A), max_B 帮B缺口)  [max版, 不累加]。返回 [P]min_keep + [P]deficit。
    """
    P = int(obs.P)
    pid = int(obs.player_id)
    kk = max(1, int(k))
    kk = min(kk, cache.cross_dist.shape[0] - 1)
    # k回合可达矩阵 reach[s,t]: s能否k回合到t
    d_k_center = cache.cross_dist[kk].to(dtype)                                   # [P,P] center dist(s@0,t@k)
    # Fleets launch from the source surface and hit the target surface.  Using
    # centre distance underestimates close-range threats on large planets, letting
    # min_keep drain planets that an adjacent enemy can actually hit this turn.
    surface_gap = (
        obs.r.to(dtype).view(P, 1)
        + float(LAUNCH_SURFACE_OFFSET)
        + obs.r.to(dtype).view(1, P)
        + float(TARGET_HIT_SURFACE_OFFSET)
    )
    d_k = (d_k_center - surface_gap).clamp(min=0.0)                               # [P,P] surface travel distance
    spd = fleet_speed(obs.ships.clamp(min=1e-6)).to(dtype)                        # [P]
    reach = (spd.view(P, 1) * float(kk)) >= d_k                                   # [P,t] s能k回合到t
    alive = obs.alive
    mine = obs.owned & alive                                                     # [P]
    enemy = alive & (obs.owner_abs >= 0) & (obs.owner_abs != pid)                # [P]
    ships = obs.ships.to(dtype)
    eye = torch.eye(P, dtype=torch.bool, device=device)
    # [v33] 在途舰队 k 回合到各星 t 的兵(arrivals_by_owner[t, 1:k+1, owner]), 按owner=me/敌 分。
    enemy_inflight = torch.zeros(P, dtype=dtype, device=device)                  # [t] 敌在途k回合到t
    friend_inflight = torch.zeros(P, dtype=dtype, device=device)                 # [t] 友在途k回合到t
    abo = getattr(garrison_status, "arrivals_by_owner", None) if garrison_status is not None else None
    if abo is not None:
        Hk = min(kk, abo.shape[1] - 1)
        arr_k = abo[:, 1:Hk + 1, :]                                                # [P, h, A] 前k回合各owner到达t
        A_ = arr_k.shape[-1]
        if pid < A_:
            friend_step, enemy_step = split_player_same_step_net(arr_k, pid)
            friend_inflight = friend_step.sum(dim=1).to(dtype)
            enemy_inflight = enemy_step.sum(dim=1).to(dtype)
    # [v67-regroup-8] Local K-window balance for regroup reserve.  For each
    # owned planet X, compare the total force both sides can project to X within
    # K turns:
    #   side_pool(X) = Σ reachable_s (ships_s + (K - eta(s,X)) * prod_s)
    # X's own production is counted separately, so current ships only need to
    # cover what allies + K turns of local production cannot cover.
    K_range = torch.arange(1, kk + 1, dtype=dtype, device=device)
    d_all_center = cache.cross_dist[1:kk + 1].to(dtype)                            # [K,P,P]
    d_all = (d_all_center - surface_gap.view(1, P, P)).clamp(min=0.0)
    can_arrive = (spd.view(1, P, 1) * K_range.view(kk, 1, 1)) >= d_all              # [K,src,tgt]
    eta_grid = K_range.view(kk, 1, 1).expand(kk, P, P)
    eta_ST = torch.where(
        can_arrive,
        eta_grid,
        torch.full_like(eta_grid, float(kk + 1)),
    ).amin(dim=0)                                                                   # [src,tgt]
    eta_ok = eta_ST <= float(kk)
    prod_P = prod.to(dtype)
    source_pool = (
        ships.view(P, 1)
        + (float(kk) - eta_ST).clamp(min=0.0) * prod_P.view(P, 1)
    )
    source_pool = torch.where(eta_ok, source_pool, torch.zeros_like(source_pool))    # [src,tgt]
    not_self = ~eye

    # 敌k可达每颗星t: 优先使用 exact future-departure schedule。旧版只按“当前敌星兵力”
    # 判断 k 窗口可达，会漏掉敌星先等几回合生产、变快、仍在 k 内打到的真实威胁。
    e_reach = reach & enemy.view(P, 1)                                           # [s,t] legacy fallback / locked fallback
    if garrison_status is not None and movement is not None:
        all_targets = torch.arange(P, dtype=torch.long, device=device)
        enemy_future = enemy_reinforcement_schedule(
            obs, cache, all_targets, prod, pid,
            K_eta=kk, device=device, dtype=dtype,
            garrison_status=garrison_status, movement=movement,
        )
        enemy_muster = enemy_future[:, kk - 1] if enemy_future.shape[-1] >= kk else torch.zeros(P, dtype=dtype, device=device)
        enemy_atk = enemy_muster + enemy_inflight
    else:
        enemy_atk = (e_reach.to(dtype) * ships.view(P, 1)).sum(dim=0) + enemy_inflight  # [t]
    # 友方k可达每颗星t(含t自身, 不含敌): Σ 我星s兵(可达) + 自身 + 友在途k到t
    f_reach = (reach | eye) & mine.view(P, 1)                                     # [s,t] 我方(含自身)
    friend_def = (f_reach.to(dtype) * ships.view(P, 1)).sum(dim=0) + friend_inflight  # [t]
    # self_gap(X) = max(0, 敌k可达X − (友方k可达X − X自身兵)) —— 守自己时不靠自己当外援
    friend_excl_self = friend_def - torch.where(mine, ships, torch.zeros_like(ships))  # [t] 不含t自身
    self_gap = (enemy_atk - friend_excl_self).clamp(min=0.0)                      # [t]
    self_gap = torch.where(mine, self_gap, torch.zeros_like(self_gap))
    self_gap_keep_P = torch.minimum(self_gap, ships)                              # [P] 自身防守需要, 不含帮邻星
    # [v67-regroup-9] Friendly force around X must be dispatchable force, not
    # total current garrison.  A front planet's current ships cannot be counted
    # as available support for multiple neighbors while also defending itself.
    dispatchable_friend_source = (ships - self_gap_keep_P).clamp(min=0.0)
    friend_source_pool = (
        dispatchable_friend_source.view(P, 1)
        + (float(kk) - eta_ST).clamp(min=0.0) * prod_P.view(P, 1)
    )
    friend_source_pool = torch.where(eta_ok, friend_source_pool, torch.zeros_like(friend_source_pool))
    friend_pool_excl_self_P = (
        friend_source_pool
        * mine.view(P, 1).to(dtype)
        * not_self.to(dtype)
    ).sum(dim=0)                                                                     # [tgt]
    local_balance_reserve_P = (
        enemy_atk
        - friend_pool_excl_self_P
        - friend_inflight
        - prod_P * float(kk)
    ).clamp(min=0.0)
    local_balance_reserve_P = torch.where(
        mine,
        torch.minimum(local_balance_reserve_P, ships),
        torch.zeros_like(local_balance_reserve_P),
    )
    # A帮邻星B缺口: 对 B(我方), 没有A时B缺口 = max(0, 敌k可达B − (友方k可达B − A对B贡献))
    #   A对B贡献 = A兵 if (A能k到B 或 A==B) else 0  → 用 f_reach[A,B]·A兵
    # gap_without_A[A,B] = max(0, enemy_atk[B] − (friend_def[B] − contrib[A,B]))
    contrib = f_reach.to(dtype) * ships.view(P, 1)                               # [A,B] A对B(我方)的可达兵贡献
    gap_wo_A = (enemy_atk.view(1, P) - (friend_def.view(1, P) - contrib)).clamp(min=0.0)  # [A,B]
    # 只对"B是我方星 且 A真的对B有贡献(contrib>0)"才算; A帮B的留守 = min(contrib, gap_wo_A)
    help_need = torch.minimum(contrib, gap_wo_A)                                  # [A,B] A为B该留
    help_need = torch.where(mine.view(1, P), help_need, torch.zeros_like(help_need))
    help_need = help_need * (~eye).to(dtype)                                      # 不算A自己(self_gap管)
    help_max = help_need.max(dim=1).values                                       # [A] 最危急邻星(max版)
    min_keep_P = torch.maximum(self_gap, help_max)                               # [P]
    min_keep_P = torch.minimum(min_keep_P, ships)                                # 封顶自身兵
    # [v33] per-planet 防守缺口 deficit = 敌k可达 − 友k可达(含自身), >0=真守不住(regroup目标用)
    deficit_P = (enemy_atk - friend_def).clamp(min=0.0)                          # [P]
    deficit_P = torch.where(mine, deficit_P, torch.zeros_like(deficit_P))
    # [v34 可靠锁定判定] 目标t"真会被我占下"(可靠, 含敌增援悲观会计) ⟺ 我方在途到t ≥ t当前garrison +
    # 敌k可达t(敌增援muster, 悲观高估无害)。不信raw do-nothing owner投影(它乐观假设敌不增援→4P假预测)。
    # 仅对当前非我的星(中立/敌)判定。返回 [P] bool。
    enemy_atk_only = enemy_atk                                                        # [t] 敌k可达(同 min_keep)
    locked_reliable_P = (~mine) & alive & (friend_inflight >= ships + enemy_atk_only)  # [P] 我在途碾压garrison+敌增援
    return (
        min_keep_P[source_idx.clamp(0, P - 1)],
        deficit_P,
        locked_reliable_P,
        min_keep_P,
        self_gap_keep_P,
        local_balance_reserve_P,
    )  # [S], [P], [P], [P], [P], [P]


def _build_comet_rescue(*, obs, obs_tensors, cache, movement, pid, wave_entries, regroup_entries,
                        device, dtype):
    """[v38] Comet 即将离场兜底: 我方占的 comet 如果 attack/regroup 都没用它当 source,
    强制全兵 launch 到最近非 comet 友方星 (LB 79748581 t81 16兵随 comet 离场全损)。
    """
    P = obs.P
    empty = LaunchEntries(
        source_slots=torch.zeros(0, dtype=torch.long, device=device),
        target_slots=torch.zeros(0, dtype=torch.long, device=device),
        ships=torch.zeros(0, dtype=dtype, device=device),
        angle=torch.zeros(0, dtype=dtype, device=device),
        eta=torch.ones(0, dtype=dtype, device=device),
        valid=torch.zeros(0, dtype=torch.bool, device=device),
    )
    comets_obj = obs_tensors.get("comets")
    if comets_obj is None:
        return empty
    paths = comets_obj.get("paths")              # [G, C, MAX_PATH, 2]
    path_index = comets_obj.get("path_index")    # [G]
    planet_ids = comets_obj.get("planet_ids")    # [G, C]
    if paths is None or path_index is None or planet_ids is None:
        return empty
    G, C, _MAX_PATH, _ = paths.shape
    planets_arr = obs_tensors["planets"]   # [P, 7]
    planet_id_to_slot = {
        int(planets_arr[i, 0].item()): i
        for i in range(P)
        if int(planets_arr[i, 0].item()) >= 0
    }
    nan_mask = torch.isnan(paths[:, 0, :, 0])    # [G, MAX_PATH]
    has_pt = ~nan_mask
    path_len = has_pt.to(torch.long).sum(dim=-1)  # [G]
    lifetime_remaining = (path_len - path_index.to(torch.long) - 1)
    # 离场前 1 回合 (含): lifetime ≤ 1
    doomed_groups = lifetime_remaining <= 1
    if not bool(doomed_groups.any()):
        return empty

    # Ships already launched from each source by attack/regroup. A doomed comet
    # may have been used only partially; rescue should move the remaining ships
    # rather than skipping the source wholesale.
    used_ships_by_source: dict[int, float] = {}
    for entries in (wave_entries, regroup_entries):
        if entries.valid.numel() > 0 and entries.valid.any():
            for s, sh in zip(
                entries.source_slots[entries.valid].tolist(),
                entries.ships[entries.valid].tolist(),
            ):
                si = int(s)
                used_ships_by_source[si] = used_ships_by_source.get(si, 0.0) + float(sh)

    # 收集即将离场的 comet 星 set (用于过滤目标, 不送给即将消失的 comet)
    doomed_planet_set = set()
    for g in range(G):
        if not bool(doomed_groups[g]) or int(path_index[g]) < 0:
            continue
        for c in range(C):
            pid_c = int(planet_ids[g, c])
            slot_c = planet_id_to_slot.get(pid_c)
            if slot_c is not None:
                doomed_planet_set.add(slot_c)

    # 收集要撤的 comet 源星: 我方占 + ships>0 + 没被用过
    rescue_srcs = []
    for g in range(G):
        if not bool(doomed_groups[g]) or int(path_index[g]) < 0:
            continue
        for c in range(C):
            pid_c = int(planet_ids[g, c])
            slot_c = planet_id_to_slot.get(pid_c)
            if slot_c is None:
                continue
            if not bool(obs.owned[slot_c]):
                continue
            ships_c = float(obs.ships[slot_c])
            if ships_c < 1.0:
                continue
            remaining_c = ships_c - used_ships_by_source.get(int(slot_c), 0.0)
            if remaining_c < 1.0:
                continue
            rescue_srcs.append((slot_c, remaining_c))

    if not rescue_srcs:
        return empty

    # 找目标: 我方非 comet 友星
    rescue_dst_mask = obs.owned & obs.alive
    for d_ in doomed_planet_set:
        if d_ < P:
            rescue_dst_mask[d_] = False
    if not bool(rescue_dst_mask.any()):
        return empty
    rescue_dst_planets = rescue_dst_mask.nonzero(as_tuple=False).reshape(-1).tolist()

    # 对每颗 comet 源星, 优先找物理上真实可达的最近友星。旧版只按直线距离
    # 选最近友星，可能把兵从 comet 撤向太阳另一侧的友星，结果 launch 后撞太阳；
    # 这里复用正式 intercept/swept screen，只有没有任何可达友星时才保留旧兜底方向。
    import math as _math
    src_list, tgt_list, ships_list, angle_list, eta_list = [], [], [], [], []
    for src_slot, ships_c in rescue_srcs:
        sp = planets_arr[src_slot]
        sx, sy = float(sp[2]), float(sp[3])
        dst_slots = [int(t) for t in rescue_dst_planets if int(t) != int(src_slot)]
        if not dst_slots:
            continue
        dst_t = torch.tensor(dst_slots, dtype=torch.long, device=device)
        src_t = torch.full_like(dst_t, int(src_slot))
        ships_t = torch.full(dst_t.shape, float(ships_c), dtype=dtype, device=device)
        aim = intercept_angle(movement, src_t, dst_t, ships_t)
        viable = aim["viable"] & torch.isfinite(aim["eta"])
        best_d, best_t = float("inf"), -1
        best_angle, best_eta = 0.0, 1.0
        if bool(viable.any()):
            eta_rank = torch.where(viable, aim["eta"], torch.full_like(aim["eta"], float("inf")))
            best_i = int(torch.argmin(eta_rank).item())
            best_t = int(dst_slots[best_i])
            best_angle = float(aim["angle"][best_i])
            best_eta = float(aim["eta"][best_i])
        # Desperate fallback: even an untracked/no-hit launch can at least move
        # ships off the source before the comet despawns; keep the old nearest
        # direction only when no screened target is reachable.
        for tgt_pid in rescue_dst_planets:
            if tgt_pid == src_slot:
                continue
            if best_t >= 0 and bool(viable.any()):
                break
            tp = planets_arr[tgt_pid]
            dx = float(tp[2]) - sx
            dy = float(tp[3]) - sy
            d = _math.hypot(dx, dy)
            if d < best_d:
                best_d = d; best_t = tgt_pid
        if best_t < 0:
            continue
        if not bool(viable.any()):
            tp = planets_arr[best_t]
            best_angle = _math.atan2(float(tp[3]) - sy, float(tp[2]) - sx)
            # ETA = 距离 / fleet_speed (近似), 仅用于 entries 占位
            sp_v = float(fleet_speed(torch.tensor(max(ships_c, 1.0))))
            best_eta = best_d / max(sp_v, 1e-6)
        src_list.append(src_slot)
        tgt_list.append(best_t)
        ships_list.append(ships_c)
        angle_list.append(best_angle)
        eta_list.append(best_eta)

    if not src_list:
        return empty

    return LaunchEntries(
        source_slots=torch.tensor(src_list, dtype=torch.long, device=device),
        target_slots=torch.tensor(tgt_list, dtype=torch.long, device=device),
        ships=torch.tensor(ships_list, dtype=dtype, device=device),
        angle=torch.tensor(angle_list, dtype=dtype, device=device),
        eta=torch.tensor(eta_list, dtype=dtype, device=device),
        valid=torch.ones(len(src_list), dtype=torch.bool, device=device),
    )


def plan_lite_waves(
    *,
    movement: PlanetMovement,
    obs,
    obs_tensors: dict,
    cache,
    garrison_status,
    prod: Tensor,
    alive_by_step: Tensor,
    config: ProducerLiteConfig,
    player_count: int,
    out_stats: dict | None = None,
):
    """Single-size, single-source attack planner + regroup.

    Builds exactly one candidate per ``(source, target)`` shortlist pair — fleet
    size = the source's max garrison launch (``safe_drain``) — scores them with the
    exact competitive flow diff, and greedily fires the best wave per target up to
    ``max_waves_per_turn``. Returns the combined ``LaunchEntries`` (attack waves ++
    regroup).
    """
    P = obs.P
    device = obs.device
    dtype = obs.ships.dtype
    pid = int(obs.player_id)

    # [v7] Runtime alive-player count: when a 4P game reduces to 2 alive,
    # switch to 2P strategy (early aggression, comet bonus, sniping all activate).
    # This uses obs data to count players with any ships/planets still alive.
    _planet_alive_owners = obs.owner_abs[obs.alive & (obs.owner_abs >= 0)]
    _fleet_alive_owners = obs.f_owner[obs.f_alive & (obs.f_owner >= 0)]
    if _planet_alive_owners.numel() and _fleet_alive_owners.numel():
        _alive_owners = torch.cat([_planet_alive_owners, _fleet_alive_owners]).unique()
    elif _planet_alive_owners.numel():
        _alive_owners = _planet_alive_owners.unique()
    else:
        _alive_owners = _fleet_alive_owners.unique()
    _live_owner_count = int(_alive_owners.numel())
    effective_pc = max(2, _live_owner_count)
    # [v30] 我方总兵占全场≥40% → 切 2P 双倍 (用户). 4P单倍prod_mode本为防火中取栗(打敌星替第三方
    # 做嫁衣), 但当"我"已是绝对领先/两强之一(占40%, 4P均分仅25%), 我就是要赢的那个——该全力打敌
    # 削弱对手、巩固领先, 不再顾虑火中取栗。对局实证(79512574): step107 我占44%但因苟活的slot1/3
    # (各1星6%)维持effective_pc=4→单倍→占敌星ROI仅0.12→不打→放任slot2滚到27星碾压。只看"我方"占比
    # (不是任意一家), 落后时不切(避免我双倍打领先者=替剩下的第三方做嫁衣)。
    if not os.environ.get("PRODUCER_NO_DOMINANT_2P"):
        _my_fleet_alive = obs.f_alive & (obs.f_owner == float(pid))
        _owned_fleet_alive = obs.f_alive & (obs.f_owner >= 0)
        _my_ships = float(
            obs.ships[obs.owned & obs.alive].sum()
            + obs.f_ships[_my_fleet_alive].sum()
        )
        _all_ships = float(
            obs.ships[obs.alive & (obs.owner_abs >= 0)].sum()
            + obs.f_ships[_owned_fleet_alive].sum()
        )
        if _all_ships > 1.0 and _my_ships / _all_ships >= 0.40 and effective_pc > 2:
            effective_pc = 2

    H_axis = int(garrison_status.ships.shape[-1])
    H = max(H_axis - 1, 0)
    K_eta = max(1, min(int(config.horizon), H))
    W = max(1, int(config.max_waves_per_turn))
    empty_entries = _empty_entries(device, dtype)

    def _rescue_only_entries():
        return _build_comet_rescue(
            obs=obs, obs_tensors=obs_tensors, cache=cache, movement=movement, pid=pid,
            wave_entries=empty_entries, regroup_entries=empty_entries,
            device=device, dtype=dtype,
        )

    source_mask = obs.owned & obs.alive & (obs.ships >= float(config.min_ships_to_launch))
    if not bool(source_mask.any()):
        return _rescue_only_entries()

    S_cap = max(1, min(int(config.max_sources_per_lane), P))
    source_idx, source_exists = _candidate_indices(obs.ships, source_mask, S_cap)
    target_idx, target_exists = build_target_shortlist(
        obs, obs_tensors, garrison_status, cache,
        config=config, K_eta=K_eta, H=H, prod=prod, source_mask=source_mask,
    )
    if not bool(target_exists.any()):
        return _rescue_only_entries()
    S = int(source_idx.shape[0])
    T = int(target_idx.shape[0])
    target_is_mine = obs.owned[target_idx.clamp(0, P - 1)]                       # [T]

    source_ships = obs.ships[source_idx.clamp(0, P - 1)].to(dtype)                # [S]
    H_eff = torch.full((), float(H), dtype=dtype, device=device)
    # [v33 安全兵力 min_keep(用户对称k攻防公式)] 每颗源星A的最小留守 = 保证"抽兵后 A 及依赖A当
    # 援军的邻星 都不从守得住变守不住"的最小自留。用对称k窗口攻防: 某星X守得住 ⟺ X兵+友方k可达X
    # ≥ 敌方k可达X。A守自己缺口 = max(0, 敌k可达A − 友方k可达A(不含A))。A帮邻星B缺口 = max(0,
    # 敌k可达B −(友方k可达B − A对B贡献))。min_keep(A)=max(守自己, max_B 帮B) [max版,不累加,
    # 假设敌一次主攻一处]。reserve=min_keep, safe_drain抽 A兵−min_keep=富余→进攻。无威胁星min_keep=0
    # →随便抽不饿死(vs prod·K无差别留)。env PRODUCER_NO_MINKEEP 关闭, PRODUCER_MINKEEP_K 调窗口(默认6)。
    # [v33/v34] 一次算出 min_keep 留守 / deficit / 可靠锁定(三者共享同一套对称k攻防量)。
    _reserve = None
    _reserve_full_P = None
    _deficit_P = None
    _locked_reliable_P = None
    _min_keep_P = None
    _self_gap_P = None
    _local_balance_reserve_P = None
    (
        _mk_reserve,
        _deficit_P,
        _locked_reliable_P,
        _min_keep_P,
        _self_gap_P,
        _local_balance_reserve_P,
    ) = _compute_min_keep(
        obs, cache, source_idx=source_idx, prod=prod,
        k=int(os.environ.get("PRODUCER_MINKEEP_K", "6")), device=device, dtype=dtype,
        garrison_status=garrison_status, movement=movement,
    )
    if not os.environ.get("PRODUCER_NO_MINKEEP"):
        _reserve_full_P = _min_keep_P.to(device=device, dtype=dtype)
        # Keep v67's default: rotating sources are attack bases and do not hold
        # min_keep reserve.  A replay-driven experiment can opt into holding
        # reserve with PRODUCER_ROT_RESERVE_MULT=1.0, but panel checks showed
        # that defaulting it on over-constrains 2p high-prod maps.
        # 用 obs.is_orbiting [P] bool 判定 (轨道半径 > 0.5 且 < ROT_RADIUS_LIMIT)。
        if not os.environ.get("PRODUCER_NO_ROT_STAT_SPLIT"):
            _stat_mult = float(os.environ.get("PRODUCER_STAT_RESERVE_MULT", "1.0"))     # 静止友星 reserve mult
            _rot_basis_P = _reserve_full_P
            if os.environ.get("PRODUCER_ROT_SUPPORTED_SELF_ONLY", "1") == "1" and _self_gap_P is not None:
                _rot_basis_P = _self_gap_P.to(device=device, dtype=dtype)
            _rot_mult_P = _rotating_reserve_multiplier(
                obs, cache, reserve_full_P=_rot_basis_P, pid=pid,
                K_eta=K_eta, device=device, dtype=dtype,
            )
            _reserve_full_P = torch.where(obs.is_orbiting, _rot_basis_P, _reserve_full_P)
            _reserve_full_P = torch.where(
                obs.is_orbiting, _reserve_full_P * _rot_mult_P, _reserve_full_P * _stat_mult,
            )
        _reserve = _reserve_full_P[source_idx.clamp(0, P - 1)]
    drain = safe_drain(
        garrison_status, source_idx=source_idx, source_ships=source_ships,
        H_eff=H_eff, player_id=pid, reserve=_reserve,
        source_prod=prod[source_idx.clamp(0, P - 1)].to(dtype),
    )                                                                            # [S]

    _drain_before_rear = drain.clone()
    _rear_cover_src_idx = None
    _rear_cover_cap = None
    _rear_cover_can = None
    _rear_cover_eta = None
    _rear_cover_release = None
    _rear_cover_eta_limit = None
    # [v67-replay-1] Experimental coupled rear-reinforce reserve release.  This
    # materializes B -> A cover launches, but panel checks showed it changes
    # resource tempo enough to regress badly, so keep it opt-in only.
    if os.environ.get("PRODUCER_REAR_REINFORCE") and _reserve is not None and _reserve_full_P is not None:
        # [v53 fix] 只用真敌方目标 (非中立): 中立距离近会让条件过严, 且打中立不需要后方增援释放
        _is_enemy_tgt = obs.alive[target_idx.clamp(0, P - 1)] & (obs.owner_abs[target_idx.clamp(0, P - 1)] >= 0) & (obs.owner_abs[target_idx.clamp(0, P - 1)] != pid)
        _enemy_tgts = target_idx[_is_enemy_tgt & target_exists]
        if _enemy_tgts.numel() > 0:
            _src_slots_rear = source_idx.clamp(0, P - 1)
            _enemy_slots_rear = _enemy_tgts.clamp(0, P - 1)
            _aim_A_E = intercept_angle(
                movement,
                _src_slots_rear.view(S, 1),
                _enemy_slots_rear.view(1, -1),
                source_ships.clamp(min=1.0).view(S, 1).expand(S, int(_enemy_slots_rear.numel())),
            )
            _eta_A_E = torch.where(
                _aim_A_E["viable"],
                _aim_A_E["eta"].to(dtype),
                torch.full_like(_aim_A_E["eta"].to(dtype), float("inf")),
            ).amin(dim=-1)                                                        # [S]
            _mine_mask = obs.owned & obs.alive                                    # [P]
            _cover_src_mask = _mine_mask & (obs.ships.to(dtype) >= 1.0)
            _cover_idx = _cover_src_mask.nonzero(as_tuple=False).squeeze(-1)      # [M]
            if _cover_idx.numel() > 0:
                _B_ships = obs.ships[_cover_idx].to(dtype)                         # [M]
                _B_reserve = _reserve_full_P[_cover_idx].to(dtype)                 # [M]
                _B_cap_safe = safe_drain(
                    garrison_status, source_idx=_cover_idx, source_ships=_B_ships,
                    H_eff=H_eff, player_id=pid, reserve=_B_reserve,
                    source_prod=prod[_cover_idx].to(dtype),
                )
                _B_cap = torch.minimum(_B_cap_safe, (_B_ships - _B_reserve).clamp(min=0.0)).floor()
                _B_live = _B_cap >= 1.0

                _aim_B_A = intercept_angle(
                    movement,
                    _cover_idx.view(-1, 1),
                    _src_slots_rear.view(1, S),
                    torch.ones((int(_cover_idx.numel()), S), dtype=dtype, device=device),
                )
                _eta_B_A = _aim_B_A["eta"].to(dtype)                              # [M,S] conservative 1-ship eta
                _can_reinforce = (
                    _aim_B_A["viable"]
                    & _B_live.view(-1, 1)
                    & source_exists.view(1, S)
                    & (_cover_idx.view(-1, 1) != _src_slots_rear.view(1, S))
                    & torch.isfinite(_eta_A_E).view(1, S)
                    & (_eta_B_A < _eta_A_E.view(1, S))
                )
                _rear_cover_release = torch.zeros_like(_reserve)
                _cap_tmp = _B_cap.clone()
                for _a in range(S):
                    if not bool(source_exists[_a]) or float(_reserve[_a]) < 1.0:
                        continue
                    _need = int(torch.floor(_reserve[_a]).item())
                    if _need <= 0:
                        continue
                    _cand_b = torch.where(_can_reinforce[:, _a] & (_cap_tmp >= 1.0))[0]
                    if int(_cand_b.numel()) == 0:
                        continue
                    _order = sorted(
                        [int(x.item()) for x in _cand_b],
                        key=lambda _bi: (float(_eta_B_A[_bi, _a].item()), int(_cover_idx[_bi].item())),
                    )
                    for _bi in _order:
                        _take = min(_need, int(torch.floor(_cap_tmp[_bi]).item()))
                        if _take <= 0:
                            continue
                        _rear_cover_release[_a] = _rear_cover_release[_a] + float(_take)
                        _cap_tmp[_bi] = _cap_tmp[_bi] - float(_take)
                        _need -= _take
                        if _need <= 0:
                            break
                if bool((_rear_cover_release >= 1.0).any()):
                    _rear_cover_src_idx = _cover_idx
                    _rear_cover_cap = _B_cap
                    _rear_cover_can = _can_reinforce
                    _rear_cover_eta = _eta_B_A
                    _rear_cover_eta_limit = _eta_A_E
                    _reserve = (_reserve - _rear_cover_release).clamp(min=0.0)
                drain = safe_drain(
                    garrison_status, source_idx=source_idx, source_ships=source_ships,
                    H_eff=H_eff, player_id=pid, reserve=_reserve,
                    source_prod=prod[source_idx.clamp(0, P - 1)].to(dtype),
                )

    # [v67-regroup-3] Reserve used later by attack scoring. Keep this source-level
    # tensor separate from candidate tensors; candidates are built below.
    _source_reserve_P = None
    _regroup_source_reserve_P = None
    if int(player_count) == 2 and effective_pc <= 2 and _min_keep_P is not None:
        _source_reserve_P = _min_keep_P.to(device=device, dtype=dtype).clamp(min=0.0)
        # [v67-regroup-8] Regroup hard reserve uses local K-window balance:
        # enemy projectable pool around this planet minus friendly projectable
        # pool and this planet's K-turn production.  Far/backline planets whose
        # production can cover a delayed attack no longer get locked as front.
        if _local_balance_reserve_P is not None:
            _regroup_source_reserve_P = _local_balance_reserve_P.to(device=device, dtype=dtype).clamp(min=0.0)

    # Uniform reach cap = K_eta (= horizon).
    eta_cap = torch.full((T,), float(K_eta), dtype=dtype, device=device)          # [T]

    # [v26] UNIFIED enemy arrival schedule per target — [T, K_eta] = enemy ships arriving
    # at target T on each future turn. Two deterministic sources, summed:
    #   (a) IN-FLIGHT: garrison_status.arrivals_by_owner — engine-exact ballistic arrivals
    #       of fleets ALREADY launched (these WILL arrive; zero uncertainty).
    #   (b) REINFORCEMENT MUSTER: enemy_reinforcement_schedule — worst-case, every enemy
    #       star scrambles its on-planet garrison NOW; each delivers garrison+prod·arr on
    #       its dynamic arrival turn. Upper bound on "what the opponent can still send".
    # This schedule feeds BOTH stages of the capture decision (用户 spec):
    #   • ships arriving BEFORE our eta → added to capture_floor (defenders we must clear),
    #   • ships arriving AFTER our eta  → race our garrison in hold(x).
    # _reinf_cumK[T, k] = total worst-case enemy defence if MY fleet lands on turn k
    # (every enemy star musters NOW: garrison + (k − its_arrival)·prod for those that
    # reach T by k). Already cumulative-by-my-arrival, NOT per-turn — index directly.
    _abo = getattr(garrison_status, "arrivals_by_owner", None)
    # [v40] 传 garrison_status: muster 用投影 ships[e, e_send_time] 取代手算 g_e+(k-arr)·prod_e,
    # 自动含 e 在派出前收到的敌方在途援军 (中转效应) + owner 变更 (e 中途被夺则归 0).
    _reinf_cumK = enemy_reinforcement_schedule(
        obs, cache, target_idx, prod, pid, K_eta=K_eta, device=device, dtype=dtype,
        garrison_status=garrison_status, movement=movement)                            # [T, K_eta]

    # [v26] capture_floor reinforcement = the muster defence at my arrival turn (用户 spec:
    # all enemy stars reaching T before me, each contributing garrison+(my_eta−arr)·prod).
    # Replaces the old `cheap_enemy_pressure·rho·0.3` magic estimate. garrison_status.ships
    # defenders already含目标自身产能+已在途弹道; this adds the still-on-planet muster.
    floor = capture_floor(
        garrison_status, target_idx=target_idx, k_max=K_eta,
        capture_overhead=1.0, player_id=pid,
        reinforcement=_reinf_cumK,                                                # [T, K_eta] direct (cumulative-by-arrival)
    )                                                                            # [T, K]
    K = int(floor.shape[-1])

    # [v25] Attack-candidate construction (delayed-launch variants, aim, capture-floor,
    # multi-source admission, packing) is framework mechanism — built by
    # build_attack_candidates. The shell only layers strategy on top (opportunity-cost
    # discount + bonuses below). DELAY深度 d∈{0..DELAY_MAX} is mechanism (depth); the
    # convex DISCOUNT CURVE is strategy and stays here.
    src_prod = prod[source_idx.clamp(0, P - 1)]                                  # [S]
    target_prod = prod[target_idx.clamp(0, P - 1)]                               # [T]
    # hold(x) threat = per-turn enemy arrivals (in-flight ballistic + reinforcement muster).
    # The recurrence cumulatively sums POST-eta arrivals to race our garrison, so it needs
    # PER-TURN values. In-flight is already per-turn; reinforcement is cumulative-by-arrival
    # so difference it back to per-turn (clamp ≥0 since the (k−arr)·prod growth makes it
    # monotone). enemy_arrivals_TK[t, j] = enemy ships hitting T on turn j.
    enemy_arrivals_TK = None
    _parts = []
    if _abo is not None:
        _friendly_arr_P, _enemy_arr_P = split_player_same_step_net(_abo, pid)      # [P, H+1] each
        _tgt = target_idx.clamp(0, P - 1)
        _parts.append(_enemy_arr_P[_tgt][:, 1:K_eta + 1].to(dtype).contiguous())  # in-flight per-turn [T,K]
    if _reinf_cumK is not None:
        # per-turn reinforcement = cumulative[k] − cumulative[k−1]
        _reinf_pt = _reinf_cumK.clone()
        _reinf_pt[:, 1:] = (_reinf_cumK[:, 1:] - _reinf_cumK[:, :-1]).clamp(min=0.0)
        _parts.append(_reinf_pt)                                                  # reinforcement per-turn [T,K]
    if _parts:
        enemy_arrivals_TK = sum(_parts)

    # [v40] 我方 muster 反扑 schedule [T, K_eta]: 我占下 T 后, 每颗友星 F 派兵到 T 在 j 帧的累积.
    # 用投影 ships[F, F_send_time]: 自动含 F 收到的我方在途援军, 再从 F 中转打 T.
    # 取代 friendly_arrivals_TK (后者仅算"直达 T", 是这个的子集).
    _friendly_cumK = friendly_reinforcement_schedule(
        obs, cache, target_idx, prod, pid, K_eta=K_eta, device=device, dtype=dtype,
        garrison_status=garrison_status, movement=movement)                            # [T, K_eta]
    # 转 per-turn (对应 enemy_arrivals_TK 的 per-turn 表示, hold(x) 内部 cumsum)
    friendly_arrivals_TK = _friendly_cumK.clone()
    friendly_arrivals_TK[:, 1:] = (_friendly_cumK[:, 1:] - _friendly_cumK[:, :-1]).clamp(min=0.0)
    if _abo is not None and int(pid) < int(_abo.shape[-1]):
        _tgt = target_idx.clamp(0, P - 1)
        friendly_arrivals_TK = (
            friendly_arrivals_TK
            + _friendly_arr_P[_tgt][:, 1:K_eta + 1].to(dtype)
        )

    _target_pre_mine_ships_TK = None
    _target_pre_owner_TK = None
    _target_pre_ships_TK = None
    _same_step_arrivals_TKA = None
    _pre_owner = getattr(garrison_status, "pre_combat_owner", None)
    _pre_ships = getattr(garrison_status, "pre_combat_ships", None)
    if _pre_owner is not None and _pre_ships is not None:
        _tgt = target_idx.clamp(0, P - 1)
        _pre_owner_TK = _pre_owner[_tgt][:, 1:K_eta + 1]
        _pre_ships_TK = _pre_ships[_tgt][:, 1:K_eta + 1].to(dtype)
        _target_pre_owner_TK = _pre_owner_TK
        _target_pre_ships_TK = _pre_ships_TK
        _target_pre_mine_ships_TK = torch.where(
            _pre_owner_TK == pid,
            _pre_ships_TK,
            torch.full_like(_pre_ships_TK, -1.0),
        )
        if _abo is not None:
            _same_step_arrivals_TKA = _abo[_tgt][:, 1:K_eta + 1, :]

    _delay_idx_S_D = torch.arange(_DELAY_MAX + 1, device=device, dtype=torch.long).view(1, -1).expand(S, -1)
    _src_for_launch_S_D = source_idx.clamp(0, P - 1).view(S, 1).expand(S, _DELAY_MAX + 1)
    _delay_idx_S_D = _delay_idx_S_D.clamp(0, movement.alive_by_step.shape[0] - 1)
    _src_alive_at_launch = movement.alive_by_step[_delay_idx_S_D, _src_for_launch_S_D]
    _src_owner_at_launch = garrison_status.owner[_src_for_launch_S_D, _delay_idx_S_D]
    _src_ships_at_launch = garrison_status.ships[_src_for_launch_S_D, _delay_idx_S_D].to(dtype)
    _source_launch_ok_SD = _src_alive_at_launch & (_src_owner_at_launch == pid)

    _ac = build_attack_candidates(
        movement=movement, cache=cache, obs=obs, player_id=pid,
        source_idx=source_idx, source_exists=source_exists,
        target_idx=target_idx, target_exists=target_exists, target_is_mine=target_is_mine,
        target_prod=target_prod,
        drain=drain, source_ships=source_ships, src_prod=src_prod,
        floor=floor, K=K, K_eta=K_eta, eta_cap=eta_cap,
        delay_max=_DELAY_MAX, P=P, S=S, T=T, device=device, dtype=dtype,
        enemy_arrivals_TK=enemy_arrivals_TK,
        friendly_arrivals_TK=friendly_arrivals_TK,
        target_pre_mine_ships_TK=_target_pre_mine_ships_TK,
        target_pre_owner_TK=_target_pre_owner_TK,
        target_pre_ships_TK=_target_pre_ships_TK,
        same_step_arrivals_TKA=_same_step_arrivals_TKA,
        capture_reinforcement_TK=_reinf_cumK,
        source_launch_ok_SD=_source_launch_ok_SD,
        source_launch_ships_SD=_src_ships_at_launch,
    )
    cand_src = _ac.cand_src; cand_send = _ac.cand_send; cand_angle = _ac.cand_angle
    cand_eta = _ac.cand_eta; cand_active = _ac.cand_active; cand_valid = _ac.cand_valid
    cand_tgt_slot = _ac.cand_tgt_slot; cand_tgt_short = _ac.cand_tgt_short
    cand_is_def = _ac.cand_is_def; cand_delay = _ac.cand_delay; cand_src_prod = _ac.cand_src_prod
    cand_hold = _ac.cand_hold
    cand_cost = _ac.cand_cost
    C = _ac.C; L = _ac.L; D = _ac.D

    # [v67-regroup-3] Source-risk patience only when 2P production is already
    # ahead.  If production is equal/behind, suppressing attacks removes the
    # pressure needed to win the front; with a production lead, risky launches from
    # planets that should keep min_keep are an avoidable opportunity cost.
    _source_risk_cost = None
    if _source_reserve_P is not None:
        _owned_now = obs.alive & (obs.owner_abs >= 0)
        if bool(_owned_now.any()):
            _owner_now = obs.owner_abs[_owned_now].long()
            _A_now = max(int(_owner_now.max().item()) + 1, int(pid) + 1, int(player_count))
            _owner_prod_now = torch.zeros(_A_now, dtype=dtype, device=device)
            _owner_prod_now.scatter_add_(0, _owner_now, prod[_owned_now].to(dtype))
            _my_prod_now = _owner_prod_now[pid] if pid < _A_now else torch.zeros((), dtype=dtype, device=device)
            _enemy_prod_now = _owner_prod_now.clone()
            if pid < _A_now:
                _enemy_prod_now[pid] = 0.0
            _enemy_best_now = _enemy_prod_now.max()
            _lead_scale = ((_my_prod_now - _enemy_best_now).clamp(min=0.0) / _enemy_best_now.clamp(min=1.0)).clamp(max=1.0)
        else:
            _lead_scale = torch.zeros((), dtype=dtype, device=device)
        if bool((_lead_scale > 0).item()):
            _src_safe_CL = cand_src.clamp(0, P - 1)
            _src_reserve_CL = _source_reserve_P[_src_safe_CL]
            _src_ships_CL = obs.ships[_src_safe_CL].to(dtype).clamp(min=1.0)
            _src_risk_share_CL = (_src_reserve_CL / _src_ships_CL).clamp(min=0.0, max=1.0)
            _offense_c = (~cand_is_def).view(C, 1).expand(C, L)
            _source_risk_cost = (
                cand_send.to(dtype)
                * _src_risk_share_CL
                * cand_active.to(dtype)
                * _offense_c.to(dtype)
            ).sum(dim=-1) * _lead_scale

    def _apply_2p_source_risk_cost(_s):
        if _source_risk_cost is None:
            return _s
        return torch.where(torch.isfinite(_s), _s - _source_risk_cost, _s)

    # [v26] EFFECTIVE-enemy mask at ARRIVAL (用户 spec): a target that is neutral NOW but
    # which the post-combat projection shows owned by an ENEMY by the turn my fleet lands
    # is, for accounting, an ENEMY star — I'll be wresting it from the opponent (double
    # production swing, enemy will defend it, 2P combat对冲). Uses garrison_status.owner
    # (engine-exact forward sim incl. enemy in-flight captures) indexed at each candidate's
    # eta. Falls back to decision-time is_enemy if projection unavailable.
    _cand_eta_idx = torch.where(
        cand_active,
        cand_eta,
        torch.zeros_like(cand_eta),
    ).amax(dim=-1).clamp(min=1.0)
    # [v30] 索引一致性修正: 占领发生在 ceil(eta)(舰队整回合落地), "到达时owner"应与 capture_floor/
    # hold 的 ceil(eta) 同回合 (planner_core 用 ceil(eta)-1 索引floor的turn轴)。旧用 round(eta):
    # eta小数<0.5时取早1回合的owner → 漏判"落地时该星已翻敌"→ combat/prod/caprate口径错判。
    # garrison_status.owner是[P,H+1](第k帧=k回合后), 故直接用 ceil(eta) 绝对回合索引。
    _eta_k = _cand_eta_idx.clamp(min=1.0).ceil().long().clamp(0, garrison_status.owner.shape[-1] - 1)  # [C]
    _proj_owner_c = garrison_status.owner[cand_tgt_slot, _eta_k]                   # [C] owner at my arrival
    _enemy_now_c = obs.is_enemy[target_idx.clamp(0, P - 1)][cand_tgt_short]        # [C] enemy at decision
    cand_is_enemy_eff = _enemy_now_c | ((_proj_owner_c >= 0) & (_proj_owner_c != pid))  # enemy now / by-arrival

    # [v21] Convex opportunity-cost discount for delayed candidates (STRATEGY, stays in
    # shell): mult = 1 − 0.08·d − 0.02·d². d=1→0.90, d=5→0.10.
    # [v37] 双表 + 30 回合 ramp: 早期表(攒兵期, d=1/2 不惩罚, d=3-6 轻惩) 线性插值到晚期表
    # (v34 原值)。鼓励"等 1-6 回合占大星"(prod=5 大星 produced 大, send 涨过 floor 后 score 大正,
    # 原 mult=0.64 削弱大星优势 → 早期保留优势让 greedy 选攒兵打大星而非贪小星)。
    # env PRODUCER_EARLY_DELAY_BOOST 控制。
    _cur_step_for_delay = int(obs_tensors["step"].reshape(-1)[0].item())
    # [v37] EARLY_DELAY_BOOST 仅 2P 生效, ramp_end=20。4P 走 v34 原公式。
    _delay_boost_on = os.environ.get("PRODUCER_EARLY_DELAY_BOOST") and effective_pc <= 2
    if _delay_boost_on:
        _ramp_end = int(os.environ.get("PRODUCER_EARLY_DELAY_END", "20"))
        _t_ramp = max(0.0, min(1.0, _cur_step_for_delay / max(_ramp_end, 1)))
        # mult_early[d=0..6] = [1.00, 1.00, 1.00, 0.90, 0.80, 0.70, 0.60]
        # mult_late[d=0..6]  = [1.00, 0.90, 0.78, 0.64, 0.48, 0.30, 0.00] (= v34 原公式)
        _mult_early = torch.tensor([1.00, 1.00, 1.00, 0.90, 0.80, 0.70, 0.60], device=device, dtype=dtype)
        _mult_late  = torch.tensor([1.00, 0.90, 0.78, 0.64, 0.48, 0.30, 0.00], device=device, dtype=dtype)
        _mult_table = _mult_early + _t_ramp * (_mult_late - _mult_early)             # [7]
        cand_delay_mult = _mult_table[cand_delay.clamp(0, 6).to(torch.long)]         # [C]
    else:
        DELAY_LIN = 0.08
        DELAY_QUAD = 0.02
        _cd = cand_delay.to(dtype)
        cand_delay_mult = (1.0 - DELAY_LIN * _cd - DELAY_QUAD * _cd * _cd).clamp(min=0.0)  # [C]

    # [v3] Player-count-specific strategy
    cur_step = int(obs_tensors["step"].reshape(-1)[0].item())
    _strat = _strat_4p if effective_pc >= 3 else _strat_2p
    eff_roi = _strat.effective_roi_threshold(config=config, cur_step=cur_step)
    # [v32 实验] roi_threshold env 覆盖(用户怀疑 ROI=0 是LB退化元凶, v20=1.5)。隔离单变量A/B用。
    _roi_ov = os.environ.get("PRODUCER_ROI_THRESHOLD")
    if _roi_ov is not None:
        eff_roi = float(_roi_ov)

    # --- Precompute bonus inputs (constant across iterations) ---
    # [v26] balance_mult (strategic-balance discount) REMOVED — it was dead code (computed,
    # never applied; the hold(x)/floor真值 path took over "near-enemy stars are worth less").
    # [v29] comet precompute REMOVED — COMET_BONUS deleted (precise occupation value already
    # ranks low-garrison comets high; A/B 零影响). Snipe/adj/weak/static/counter bonuses stay.
    # [v30] 全部魔法 bonus(snipe/adj/weak/static/counter)已删除——逐个 A/B(30局×2环境)确认
    # 单独关任一都零影响(2P 66-72%/4P 30-33% 全噪声内, counter关2P反涨), 整体关也零影响。它们是
    # v8-v10 时代账本不精确时的补偿系数, v26 收益账本化(produced/combat/hold/caprate/cand_cost)后
    # 全部冗余, 与已删的 comet/def_bonus/balance_mult 同类。让精确账本完全说话(铁律4: 补偿性可删)。

    def _apply_all_bonuses(s):
        """[v30] 魔法 bonus 全删后, 这里只剩 delay 机会成本折扣(独立机制, 非魔法bonus层)。
        收益排序完全由精确账本(produced/combat/hold/caprate/cand_cost)+ROI-ratio 决定。
        历史: balance_mult/def_bonus(v26删) + comet(v29删) + snipe/adj/weak/static/counter(v30删),
        全是账本精确化后冗余的补偿系数, 逐个A/B零影响。"""
        # [v20] Delay opportunity-cost discount (only to positive scores)
        s = torch.where(torch.isfinite(s) & (s > 0), s * cand_delay_mult, s)
        return s

    # [v26] UNIFIED cost accounting (真值表, all candidates one scale):
    #   2P enemy → none(1): my losses cancel the enemy's (对冲), trade is even.
    #   neutral OR 3P/4P enemy → self(2): no 对冲, my combat loss is a real net cost.
    # [v26] uses ARRIVAL-effective enemy (incl. neutrals the enemy will have captured by
    # the time I land — those are 2P 对冲 trades too).
    _tgt_enemy_cm = cand_is_enemy_eff                                             # [C]
    if effective_pc < 3:
        cand_combat_mode = torch.where(
            _tgt_enemy_cm, torch.ones(C, dtype=torch.long, device=device),
            torch.full((C,), 2, dtype=torch.long, device=device))
    else:
        cand_combat_mode = torch.full((C,), 2, dtype=torch.long, device=device)

    # [v31] **4P suppression 折扣(用户验证方向 + 8局LB全r2根因修正)**: 4P 打敌 combat=self 把"清敌
    # garrison 的战损"全额算净损 → 打敌 score 系统性≤0 → 兵囤后方大星打不出去(单星囤657兵发0波)→
    # regroup空转 → 早期领先却停扩张被雪球反超(8局6局终0星)。但 blanket none 理论错(用户点破: 4P里
    # A打B则C/D相对变强=king-making真实成本; a1k0n也警告"不能砍combat")。正解 = 战损 × (1 − 该敌占比):
    # 占比 = 该敌总星 / 全敌总星。打"占全场敌方大头的主敌" → scale→0 → 战损≈不计(削主威胁不是做嫁衣);
    # 打苟活小虾米 → scale→1 → 全额战损(打它=替强敌清场)。这是 self/none 间按"做嫁衣比例"的精确插值,
    # 零魔法值(占比纯对局算)。8局诊断: 转折期主敌普遍占80-100% → 实战≈none解锁打敌, 但真三方均势时
    # 保留king-making成本。仅作用于敌目标的combat项。env PRODUCER_NO_SUPPRESS 回退(scale=1=纯self)。
    if effective_pc >= 3 and not os.environ.get("PRODUCER_NO_SUPPRESS"):
        _en_mask = obs.is_enemy & obs.alive                                       # [P]
        _owners = obs.owner_abs.long()
        # [v45] share = max(兵力占比, 星数占比) (用户洞察): 兵力先于星数变化, 攒兵爆发期兵力 share
        # 高 (P1 t44 兵 288 → share 0.66); 但稳定占据期星数 share 高 (15 颗小星稳产却兵不多).
        # 取 max 兼顾两种"主敌"——攒兵突袭型 + 稳定雪球型. 任一维度领先都触发压制.
        # 实测 80003074 t44: 星数 0.44 / 兵力 0.66 → max=0.66 → scale=0.34 (敢压制).
        # env PRODUCER_SUPPRESS_BY_STARS=1 回退纯星数; PRODUCER_SUPPRESS_BY_SHIPS=1 回退纯兵力.
        _by_stars = bool(os.environ.get("PRODUCER_SUPPRESS_BY_STARS"))
        _by_ships = bool(os.environ.get("PRODUCER_SUPPRESS_BY_SHIPS"))
        _en_owner_ids = _owners[_en_mask]
        _max_owner = int(_owners.max().item()) + 1 if _owners.numel() else 1
        # 星数 share
        _per_owner_star = torch.zeros(_max_owner, dtype=dtype, device=device)
        _per_owner_star.scatter_add_(0, _en_owner_ids, torch.ones_like(_en_owner_ids, dtype=dtype))
        _tot_star = float(_en_mask.sum())
        # 兵力 share
        _en_ships = obs.ships[_en_mask].to(dtype)
        _per_owner_ship = torch.zeros(_max_owner, dtype=dtype, device=device)
        _per_owner_ship.scatter_add_(0, _en_owner_ids, _en_ships)
        _tot_ship = float(_en_ships.sum())
        # 取 max (默认) 或单一维度 (env 覆盖)
        if _by_stars:
            _per_owner = _per_owner_star
            _tot = _tot_star
        elif _by_ships:
            _per_owner = _per_owner_ship
            _tot = _tot_ship
        else:
            # 默认: max(star_share, ship_share). 两份都按各自总量归一化, 然后 max 合并.
            _star_share = _per_owner_star / max(_tot_star, 1e-6)
            _ship_share = _per_owner_ship / max(_tot_ship, 1e-6)
            _per_owner = torch.maximum(_star_share, _ship_share)
            _tot = 1.0  # 已归一化, 后面除 1
        if _tot > 0:
            _share_P = torch.zeros(P, dtype=dtype, device=device)
            _share_P[_en_mask] = _per_owner[_en_owner_ids] / _tot
            _owner_share = torch.zeros_like(_share_P)
            _owner_n = min(int(_owner_share.shape[0]), int(_per_owner.shape[0]))
            if _owner_n > 0:
                _owner_share[:_owner_n] = _per_owner[:_owner_n] / _tot
            _cur_tgt_share = _share_P[cand_tgt_slot.clamp(0, P - 1)]
            _proj_owner_safe = _proj_owner_c.clamp(0, P - 1)
            _proj_tgt_share = torch.where(
                (_proj_owner_c >= 0) & (_proj_owner_c != pid),
                _owner_share[_proj_owner_safe],
                _cur_tgt_share,
            )
            _tgt_share = torch.where(_enemy_now_c, _cur_tgt_share, _proj_tgt_share)
            cand_combat_scale = torch.where(
                _tgt_enemy_cm, (1.0 - _tgt_share).clamp(0.0, 1.0),
                torch.ones(C, dtype=dtype, device=device))
        else:
            cand_combat_scale = torch.ones(C, dtype=dtype, device=device)
    else:
        cand_combat_scale = None

    # [v34 = v33 + 冗余波 combat 归零(改动二, 用户 bug 79570077)] 对"目标已被我在途友军可靠锁定"的
    # 候选, combat项归零(冗余波不该重复砸)。**用可靠判据(含敌增援悲观会计), 非raw do-nothing投影。**
    # 4P劣化真因: raw owner投影乐观假设敌不增援→预测"会夺下敌星"=假(敌实际守住)→归零→停手→真没夺下。
    # 可靠锁定 = 我方在途到t ≥ t当前garrison + 敌k可达增援(悲观高估敌, 墙1: 悲观无害)→敌星也能用、不被假
    # 预测坑。env PRODUCER_NO_LOCKED_FIX 关闭。
    if (not os.environ.get("PRODUCER_NO_LOCKED_FIX")) and _locked_reliable_P is not None:
        # [v34 判据可切] 默认=可靠判据(碾压敌增援)。PRODUCER_LOCKED_RAW=1 → 用raw do-nothing投影
        # (实测中立86-89%/4P敌94%准, 仅2P敌64%差)。用于A/B对比两种判据。
        if os.environ.get("PRODUCER_LOCKED_RAW"):
            _owner_h = garrison_status.owner[..., 1:]
            _locked = (_owner_h == pid).any(dim=-1) & (~obs.owned) & obs.alive
        else:
            _locked = _locked_reliable_P
        _cand_locked_target = _locked[cand_tgt_slot.clamp(0, P - 1)]              # [C]
        _cand_locked_at_arrival = _proj_owner_c == pid
        _cand_locked = _cand_locked_target & _cand_locked_at_arrival
        if bool(_cand_locked.any()):
            if cand_combat_scale is None:
                cand_combat_scale = torch.ones(C, dtype=dtype, device=device)
            cand_combat_scale = torch.where(_cand_locked, torch.zeros_like(cand_combat_scale), cand_combat_scale)

    # [v23/v25] Production accounting mode. Capturing an ENEMY star is normally scored
    # "double": I gain its production AND the owner loses it (prod_score = prod_me −
    # prod_opp). In 2P (1v1) that's correct — the owner's loss IS my competitive gain.
    # With 3+ players, trading blows with one opponent mainly profits the OTHER
    # bystanders (火中取栗) — the "owner loses it" half is a reward I don't fully
    # collect, so 4P scores enemy captures SINGLE (prod_me only, mode 1=self_prod).
    # The arrival-turn garrison (grows with the enemy's prod) is handled by capture_floor
    # independently, so attack COST is still charged in full — only the double-reward changes.
    #
    # [v30] 3P 中间档(用户: 比4P激进、比2P保守, 全无魔法值). 把"激进"拆成两条已有的离散轴:
    #   prod 轴: full双倍(信用削弱敌人) ←激进 / self_prod单倍 ←保守
    #   combat 轴(上方335): none不计战损(对冲) ←激进 / self计我方真实战损 ←保守
    # 2P=(full, none)双激进; 4P=(self_prod, self)双保守; **3P=(full, self)** —— prod取激进端
    # (3人时局面更接近"两强相争", 削弱直接对手的产能有真实竞争价值, 没4P那么多旁观者坐收),
    # 但 combat 仍取保守端(3人下战损依然可能被第三方趁机收割, 诚实计战损)。aggression 单调:
    # 2P > 3P > 4P, 不引入任何新系数。env PRODUCER_NO_3P_TIER 关闭→3P退回4P(self_prod)。
    _prod_double_pc = 4 if not os.environ.get("PRODUCER_NO_3P_TIER") else 3
    if effective_pc >= _prod_double_pc:
        cand_prod_mode = torch.where(
            cand_is_enemy_eff, torch.ones(C, dtype=torch.long, device=device),
            torch.zeros(C, dtype=torch.long, device=device))                     # 1=self_prod for enemy, else 0=full
    else:
        cand_prod_mode = torch.zeros(C, dtype=torch.long, device=device)         # 2P & 3P: full (double)

    # [v26] Production hold-truncation fraction: produced_delta assumes holding to the
    # horizon (prod·(H−eta)). cand_hold (deterministic recurrence, all enemies depart now)
    # is the turns we actually keep T. frac = min(H−eta, hold)/(H−eta) scales produced to
    # real hold. Neutral/safe → hold≈H → frac≈1; enemy-territory → short hold → produced削.
    _eta_c = _cand_eta_idx
    _eta_turn_c = _eta_c.ceil().clamp(min=1.0)
    _window = (float(K_eta) - _eta_turn_c).clamp(min=1.0)                        # [C] integer production turns after landing
    _hold_c = cand_hold.clamp(min=0.0, max=float(K_eta))                         # [C]
    cand_prod_hold_frac = (torch.minimum(_window, _hold_c) / _window).clamp(0.0, 1.0)  # [C]

    # [v26] ENEMY-capture success-rate discount (eta-keyed, data-calibrated to H=30).
    # The probability we actually CAPTURE an enemy star falls monotonically with eta — the
    # longer our fleet is in transit, the more turns the opponent has to reinforce/rebuild
    # (their free will, which no projection foresees). 用户: 超远星不该硬禁,而是收益按
    # 成功率打折(让账本自己排除赔本的超远攻击)。Measured H=30 enemy capture rate:
    # eta≤4 ≈ .96, eta6 ≈ .78, eta10 ≈ .68, eta14 ≈ .38, eta18 ≈ .55. Steeper fit than v1:
    # p(eta) = clamp(1 − 0.055·(eta−4), 0.30, 1). NEUTRAL stars stay 90-100% at any eta
    # (they don't react) → NO discount. Multiplies produced by P(we take the star).
    _CAPSLOPE = 0.030
    _CAPFLOOR = 0.45
    _tgt_en_c = cand_is_enemy_eff                                                 # [C] enemy at arrival (incl. flips)
    _caprate = (1.0 - _CAPSLOPE * (_eta_c - 4.0)).clamp(min=_CAPFLOOR, max=1.0)   # [C] enemy capture prob
    _caprate = torch.where(_tgt_en_c, _caprate, torch.ones_like(_caprate))        # neutrals → 1.0
    cand_prod_hold_frac = cand_prod_hold_frac * _caprate

    # [v67-replay-1] 2P neutral payback correction.
    # A target that is neutral now but projected enemy-owned by our arrival is
    # already accounted as an enemy target by cand_is_enemy_eff above (combat,
    # production, caprate, and staging use that mask).  The old hard preclaim
    # ban is kept only as an opt-in replay experiment.  For pure 2P neutral
    # captures, charge one extra neutral-garrison cost so the score must recover
    # roughly 2 * neutral_ships, not just the one-sided neutral combat loss.
    _neutral_now_c_for_gate = obs.is_neutral[cand_tgt_slot.clamp(0, P - 1)]
    _neutral_preclaim_ban = torch.zeros(C, dtype=torch.bool, device=device)
    if (
        os.environ.get("PRODUCER_NEUTRAL_PRECLAIM_BAN")
        and not os.environ.get("PRODUCER_NO_NEUTRAL_PRECLAIM_BAN")
    ):
        _owner_future = garrison_status.owner[cand_tgt_slot.clamp(0, P - 1), 1:K_eta + 1]
        _enemy_future = (_owner_future >= 0) & (_owner_future != pid)
        _turns_future = torch.arange(1, K_eta + 1, dtype=dtype, device=device).view(1, K_eta)
        _never_enemy = torch.full((C, K_eta), float(K_eta + 999), dtype=dtype, device=device)
        _first_enemy_turn = torch.where(_enemy_future, _turns_future.expand(C, K_eta), _never_enemy).min(dim=1).values
        _preclaim_lead = _eta_turn_c - _first_enemy_turn
        _neutral_preclaim_ban = (
            cand_valid
            & (~cand_is_def)
            & _neutral_now_c_for_gate
            & (_first_enemy_turn < _eta_turn_c)
            & (_preclaim_lead >= float(os.environ.get("PRODUCER_NEUTRAL_PRECLAIM_LEAD", "4.0")))
        )

    _neutral_payback_extra_cost = torch.zeros(C, dtype=dtype, device=device)
    if (
        int(player_count) == 2
        and effective_pc <= 2
        and not os.environ.get("PRODUCER_NO_2P_NEUTRAL_PAYBACK_GATE")
    ):
        _neutral_ships_c = obs.ships[cand_tgt_slot.clamp(0, P - 1)].to(dtype)
        _pure_neutral_capture = (
            cand_valid
            & (~cand_is_def)
            & (~cand_is_enemy_eff)
            & _neutral_now_c_for_gate
        )
        _payback_mult = torch.full(
            (C,),
            float(os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_MULT", "1.0")),
            dtype=dtype,
            device=device,
        )
        _payback_mode = os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_MODE", "combo").lower()
        if _payback_mode in ("time", "combo"):
            _time_start = float(os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_TIME_START", "35"))
            _time_full = float(os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_TIME_FULL", "90"))
            _den = max(_time_full - _time_start, 1.0)
            _time_factor = max(0.0, min(1.0, (float(cur_step) - _time_start) / _den))
            _payback_mult = _payback_mult * float(_time_factor)
        if _payback_mode in ("enemy", "combo"):
            _enemy_src = (obs.alive & (obs.owner_abs >= 0) & (obs.owner_abs != int(pid))).nonzero(as_tuple=False).squeeze(-1)
            if _enemy_src.numel() > 0:
                _tgt_slots_pb = cand_tgt_slot.clamp(0, P - 1)
                _d_enemy = cache.cross_dist[0].to(dtype)[_enemy_src][:, _tgt_slots_pb]
                _surface_gap_pb = (
                    obs.r.to(dtype)[_enemy_src].view(-1, 1)
                    + float(LAUNCH_SURFACE_OFFSET)
                    + obs.r.to(dtype)[_tgt_slots_pb].view(1, C)
                    + float(TARGET_HIT_SURFACE_OFFSET)
                )
                _d_enemy = (_d_enemy - _surface_gap_pb).clamp(min=0.0)
                _enemy_speed = fleet_speed(obs.ships.to(dtype)[_enemy_src].clamp(min=1e-6)).view(-1, 1).clamp(min=1e-6)
                _enemy_eta = (_d_enemy / _enemy_speed).amin(dim=0)
                _near_eta = float(os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_ENEMY_NEAR_ETA", "6.0"))
                _far_eta = float(os.environ.get("PRODUCER_2P_NEUTRAL_PAYBACK_ENEMY_FAR_ETA", "14.0"))
                _enemy_factor = ((_far_eta - _enemy_eta) / max(_far_eta - _near_eta, 1.0)).clamp(min=0.0, max=1.0)
            else:
                _enemy_factor = torch.zeros(C, dtype=dtype, device=device)
            _payback_mult = _payback_mult * _enemy_factor
        _neutral_payback_extra_cost = torch.where(
            _pure_neutral_capture,
            _neutral_ships_c * _payback_mult,
            torch.zeros_like(_neutral_ships_c),
        )

    def _apply_neutral_adjustments(_s):
        if bool(_neutral_preclaim_ban.any()):
            _s = torch.where(_neutral_preclaim_ban, torch.full_like(_s, float("-inf")), _s)
        if bool((_neutral_payback_extra_cost > 0).any()):
            _s = torch.where(torch.isfinite(_s), _s - _neutral_payback_extra_cost, _s)
        return _s

    # [v61] 2P timely-defense decay. A fleet sent to my own planet is only a
    # defense if it lands close to the enemy pressure window. Late arrivals are
    # really recaptures, so keep them possible but sharply reduce their score.
    _late_defense_score_mult = None
    if (
        int(player_count) == 2
        and effective_pc <= 2
        and cur_step >= int(os.environ.get("PRODUCER_LATE_DEF_DECAY_START", "50"))
        and enemy_arrivals_TK is not None
    ):
        _enemy_arr_TK = enemy_arrivals_TK.to(dtype)
        _has_enemy_eta = _enemy_arr_TK > 1e-6
        if bool(_has_enemy_eta.any()):
            _K_e = int(_enemy_arr_TK.shape[-1])
            _turn_grid = torch.arange(1, _K_e + 1, dtype=dtype, device=device)
            _never_eta = torch.full_like(_enemy_arr_TK, float(_K_e + 999))
            _enemy_first_eta_T = torch.where(
                _has_enemy_eta,
                _turn_grid.view(1, _K_e).expand_as(_enemy_arr_TK),
                _never_eta,
            ).min(dim=1).values                                                    # [T]
            _enemy_eta_c = _enemy_first_eta_T[cand_tgt_short.clamp(0, T - 1)]       # [C]
            _late_turns = (_eta_c.ceil().clamp(min=1.0) - (_enemy_eta_c + 1.0)).clamp(min=0.0)
            _late_def = cand_valid & cand_is_def & (_enemy_eta_c <= float(_K_e)) & (_late_turns > 0.0)
            _late_mult = torch.exp(-0.42 * _late_turns).clamp(min=0.15, max=1.0)
            _late_defense_score_mult = torch.where(
                _late_def,
                _late_mult,
                torch.ones(C, dtype=dtype, device=device),
            )

    def _apply_2p_late_defense_decay(_s):
        if _late_defense_score_mult is None:
            return _s
        return torch.where(torch.isfinite(_s) & (_s > 0), _s * _late_defense_score_mult, _s)

    # [v61] Strong big-long-uncertain penalty. Penalize large long flights
    # unless the ledger says the capture/hold is highly reliable.
    _big_long_uncertain_mult = None
    if int(player_count) == 2 and effective_pc <= 2 and cur_step >= int(os.environ.get("PRODUCER_BIG_LONG_START", "50")):
        _send_c = cand_send.sum(dim=-1) if cand_send.dim() > 1 else cand_send
        _my_fleet = obs.f_alive & (obs.f_owner == float(pid))
        _my_total_ships = (
            obs.ships[obs.owned & obs.alive].to(dtype).sum()
            + obs.f_ships[_my_fleet].to(dtype).sum()
        ).clamp(min=1.0)
        _send_frac = _send_c.to(dtype) / _my_total_ships
        _eta_turn = _eta_c.ceil().clamp(min=1.0)
        _uncertain = cand_prod_hold_frac < float(os.environ.get("PRODUCER_BIG_LONG_HOLD_FRAC", "0.90"))
        _big_long = (
            (_send_frac >= float(os.environ.get("PRODUCER_BIG_LONG_SEND_FRAC", "0.10")))
            & (_eta_turn >= float(os.environ.get("PRODUCER_BIG_LONG_ETA", "7")))
        )
        _big_long_mask = cand_valid & _big_long & _uncertain
        _over_eta = (_eta_turn - 6.0).clamp(min=0.0)
        _big_long_decay = torch.exp(-0.30 * _over_eta).clamp(min=0.20, max=1.0)
        _big_long_uncertain_mult = torch.where(
            _big_long_mask,
            _big_long_decay,
            torch.ones(C, dtype=dtype, device=device),
        )

    def _apply_2p_big_long_uncertain_penalty(_s):
        if _big_long_uncertain_mult is None:
            return _s
        return torch.where(torch.isfinite(_s) & (_s > 0), _s * _big_long_uncertain_mult, _s)

    def _low_rotating_neutral_release_enabled() -> bool:
        if not (int(player_count) == 4 and _live_owner_count >= 4):
            return False
        if cur_step >= int(os.environ.get("PRODUCER_LOW_NEUTRAL_BAN_RELEASE_END", "50")):
            return False
        _initial_planets_for_ban = obs_tensors.get("initial_planets")
        if _initial_planets_for_ban is not None:
            _initial_alive_for_ban = _initial_planets_for_ban[..., 0] >= 0
            _ban_map_prod_total = float(
                _initial_planets_for_ban[..., 6][_initial_alive_for_ban].to(dtype).sum().item()
            )
        else:
            _ban_map_prod_total = float(prod[obs.alive].to(dtype).sum().item())
        if _ban_map_prod_total >= float(os.environ.get("PRODUCER_RACE_MP_MED_LOW", "64")):
            return False
        _rot_alive = obs.alive & obs.is_orbiting
        _stat_alive = obs.alive & ~obs.is_orbiting
        _rot_prod = float(prod[_rot_alive].to(dtype).sum().item()) if bool(_rot_alive.any()) else 0.0
        _stat_prod = float(prod[_stat_alive].to(dtype).sum().item()) if bool(_stat_alive.any()) else 0.0
        _rot_share = _rot_prod / max(_rot_prod + _stat_prod, 1.0)
        _big_rot_prod = float(prod[_rot_alive].to(dtype).max().item()) if bool(_rot_alive.any()) else 0.0
        _big_stat_prod = float(prod[_stat_alive].to(dtype).max().item()) if bool(_stat_alive.any()) else 0.0
        return (
            _rot_share >= float(os.environ.get("PRODUCER_LOW_ROT_RELEASE_SHARE", "0.55"))
            and _big_rot_prod >= _big_stat_prod
        )

    # --- Initial score (same as v10) ---
    cand_delay_cl = cand_delay.view(C, 1).expand(C, L)
    launches = make_launch_set(
        source_slots=cand_src,
        target_slots=cand_tgt_slot.unsqueeze(-1).expand(C, L),
        ships=cand_send, eta=cand_eta,
        valid=cand_active & cand_valid.unsqueeze(-1),
        player_id=pid, depart_turn=cand_delay_cl,
    )
    score = score_candidates(
        garrison_status, prod=prod, alive_by_step=alive_by_step,
        player_count=int(player_count), launches=launches, player_id=pid,
        combat_mode=cand_combat_mode, prod_mode=cand_prod_mode, prod_hold_frac=cand_prod_hold_frac,
        combat_scale=cand_combat_scale,
    )
    # [v47] 前线源星禁打中立约束 (用户洞察 replay 80046504): 源星 k=6 内有敌方 fleet 在途
    # 时, 该源不得派兵打中立 (中立为后方扩张, 前线急着守不能再分兵)。仍允许打敌方 (削敌
    # 收益) 和派给友方 (regroup 集结)。env PRODUCER_NO_FRONTLINE_NEUTRAL_BAN 关闭。
    if not os.environ.get("PRODUCER_NO_FRONTLINE_NEUTRAL_BAN"):
        # 算每个源星 k=6 内敌方 inflight 到达兵数
        _abo_v47 = getattr(garrison_status, "arrivals_by_owner", None)
        if _abo_v47 is not None:
            _, _en_net_v47 = split_player_same_step_net(_abo_v47, pid)
            _en_inflight_to_p = _en_net_v47[:, 1:7].sum(dim=-1)                  # [P]
            _src_under_threat = _en_inflight_to_p[source_idx.clamp(0, P - 1)] > 0       # [S]
            # 每个 candidate: src 是前线 + 目标是中立 → score = -inf
            _is_neutral_c = ~cand_is_enemy_eff & ~cand_is_def                            # [C] 中立目标
            _src_threat_CL = _en_inflight_to_p[cand_src.clamp(0, P - 1)] > 0
            _cand_src_threat = (_src_threat_CL & cand_active).any(dim=-1)               # [C]
            _ban_mask = _cand_src_threat & _is_neutral_c                                # [C] 该候选被禁
            if _low_rotating_neutral_release_enabled():
                _ban_mask = _ban_mask & ~_is_neutral_c
            score = torch.where(_ban_mask, torch.full_like(score, float("-inf")), score)
    score = torch.where(cand_valid, score, torch.full_like(score, float("-inf")))
    score = _apply_neutral_adjustments(score)
    score = _apply_2p_source_risk_cost(score)
    score = _apply_2p_late_defense_decay(score)
    score = _apply_2p_big_long_uncertain_penalty(score)
    score = _apply_all_bonuses(score)

    # Regroup may only spend ships that do not have a better immediate/future job.
    # Candidate scoring already prices expansion, defence and offence with the
    # exact combat/hold ledger.  For every positive candidate involving source A,
    # keep the current ships needed to make that candidate affordable after its
    # planned delay; only surplus above this opportunity cost is free to regroup.
    _opportunity_keep_P = None
    if int(player_count) == 2 and effective_pc <= 2:
        _positive_candidate = cand_valid & torch.isfinite(score) & (score > float(eff_roi))
        if bool(_positive_candidate.any()):
            _delay_cur_CL = cand_delay.to(dtype).view(C, 1) * cand_src_prod.to(dtype)
            _keep_CL = (cand_send.to(dtype) - _delay_cur_CL).clamp(min=0.0)
            _keep_active = cand_active & _positive_candidate.view(C, 1) & (_keep_CL > 0.0)
            if bool(_keep_active.any()):
                _opportunity_keep_P = torch.zeros(P, dtype=dtype, device=device)
                _keep_src = cand_src[_keep_active].clamp(0, P - 1).long()
                _keep_val = _keep_CL[_keep_active]
                if hasattr(_opportunity_keep_P, "scatter_reduce_"):
                    _opportunity_keep_P.scatter_reduce_(
                        0, _keep_src, _keep_val, reduce="amax", include_self=True,
                    )
                else:
                    for _src_p in _keep_src.unique():
                        _m = _keep_src == _src_p
                        _opportunity_keep_P[_src_p] = _keep_val[_m].max()

    # [v63] 2P regroup should move idle ships toward planets that are
    # better next-wave launchpads, not just toward high pressure. On low-production
    # maps, low-efficiency neutral positives can freeze necessary pressure moves,
    # so staging/pending tracks enemy attacks by default. Low mixed-static maps
    # keep the v62-regroup-5 all-offense staging signal because neutral staging
    # there behaves like local mustering. Reuse existing production/static-count
    # boundaries; keep mostly-static maps on the enemy-only path.
    regroup_staging_value = None
    positive_offense_candidate = None
    if int(player_count) == 2 and effective_pc <= 2:
        _ctgt_stage = cand_tgt_slot.clamp(0, P - 1)
        _target_mine_stage = obs.owned[_ctgt_stage]
        _initial_planets_stage = obs_tensors.get("initial_planets")
        if _initial_planets_stage is not None:
            _stage_initial_alive = _initial_planets_stage[..., 0] >= 0
            _stage_map_prod_total = float(_initial_planets_stage[..., 6][_stage_initial_alive].to(dtype).sum().item())
        else:
            _stage_map_prod_total = float(prod[obs.alive].to(dtype).sum().item())
        _stage_low_prod = _stage_map_prod_total < float(os.environ.get("PRODUCER_RACE_MP_MED_LOW", "64"))
        _stage_base_alive = obs.alive
        if _initial_planets_stage is not None:
            _stage_base_alive = _stage_initial_alive
            _stage_comet_ids = obs_tensors.get("comet_planet_ids")
            if _stage_comet_ids is not None:
                _stage_valid_comets = _stage_comet_ids.long()
                _stage_valid_comets = _stage_valid_comets[_stage_valid_comets >= 0]
                if int(_stage_valid_comets.numel()) > 0:
                    _stage_planet_ids = _initial_planets_stage[..., 0].long()
                    _stage_is_comet = (
                        _stage_planet_ids.unsqueeze(-1) == _stage_valid_comets.view(1, -1)
                    ).any(dim=-1)
                    _stage_base_alive = _stage_base_alive & ~_stage_is_comet
        _stage_rot_count = int((_stage_base_alive & obs.is_orbiting).sum().item())
        _stage_static_count = int((_stage_base_alive & ~obs.is_orbiting).sum().item())
        _stage_mixed_static = (
            _stage_static_count >= int(os.environ.get("PRODUCER_LOW_PENDING_STATIC_COUNT_MIN", "16"))
            and _stage_static_count == 2 * max(_stage_rot_count, 1)
        )
        _stage_enemy_only = _stage_low_prod and not _stage_mixed_static
        _stage_target_ok = (
            cand_is_enemy_eff
            if _stage_enemy_only
            else torch.ones_like(cand_is_enemy_eff, dtype=torch.bool)
        )
        positive_offense_candidate = (
            cand_valid
            & (~cand_is_def)
            & (~_target_mine_stage)
            & _stage_target_ok
            & torch.isfinite(score)
            & (score > float(eff_roi))
        )
        regroup_staging_value = torch.zeros(P, dtype=dtype, device=device)
        if bool(positive_offense_candidate.any()):
            _stage_mask = positive_offense_candidate.view(C, 1) & cand_active
            _stage_src = cand_src[_stage_mask].clamp(0, P - 1).long()
            _stage_val = score.view(C, 1).expand(C, L)[_stage_mask].to(dtype).clamp(min=0.0)
            if hasattr(regroup_staging_value, "scatter_reduce_"):
                regroup_staging_value.scatter_reduce_(
                    0, _stage_src, _stage_val, reduce="amax", include_self=True,
                )
            else:
                for _src_p in _stage_src.unique():
                    _m = _stage_src == _src_p
                    regroup_staging_value[_src_p] = _stage_val[_m].max()

    # [v59] Conservative 4P production-share race bonus. This does NOT replace
    # score; score still gates feasibility in _greedy_select. The bonus only nudges
    # the ROI ranking among already score-positive candidates toward captures that
    # improve my production-share margin versus the current enemy production leader.
    race_rank_value = None
    _planet_live_owners = obs.owner_abs[obs.alive & (obs.owner_abs >= 0)]
    _fleet_live_owners = obs.f_owner[obs.f_alive & (obs.f_owner >= 0)]
    if _planet_live_owners.numel() and _fleet_live_owners.numel():
        _live_owners = torch.cat([_planet_live_owners, _fleet_live_owners]).unique()
    elif _planet_live_owners.numel():
        _live_owners = _planet_live_owners.unique()
    else:
        _live_owners = _fleet_live_owners.unique()
    _all_four_alive = int(_live_owners.numel()) >= 4
    if (
        effective_pc >= 4
        and _all_four_alive
        and cur_step < int(os.environ.get("PRODUCER_RACE_END", "80"))
        and not os.environ.get("PRODUCER_NO_RACE_ROI")
    ):
        _owned_alive = obs.alive & (obs.owner_abs >= 0)
        _max_owner = int(obs.owner_abs[_owned_alive].max().item()) if bool(_owned_alive.any()) else 0
        _A = max(int(player_count), _max_owner + 1, pid + 1)
        _owner_prod = torch.zeros(_A, dtype=dtype, device=device)
        if bool(_owned_alive.any()):
            _owner_prod.scatter_add_(
                0,
                obs.owner_abs[_owned_alive].long().clamp(0, _A - 1),
                prod[_owned_alive].to(dtype),
            )
        _total_prod0 = _owner_prod.sum().clamp(min=1.0)
        _my_prod0 = _owner_prod[pid] if pid < _A else torch.zeros((), dtype=dtype, device=device)
        _enemy0 = _owner_prod.clone()
        if pid < _A:
            _enemy0[pid] = -float("inf")
        _leader_prod0 = _enemy0.max().clamp(min=0.0)
        _margin0 = (_my_prod0 - _leader_prod0) / _total_prod0

        _ctgt = cand_tgt_slot.clamp(0, P - 1)
        _target_prod_c = prod[_ctgt].to(dtype)                                    # [C]
        _target_mine_now = obs.owned[_ctgt]                                       # [C]
        _offensive_c = (~cand_is_def) & (~_target_mine_now)

        # Owner before my capture: prefer projected arrival owner when it is an
        # enemy; otherwise use current enemy owner; otherwise neutral (-1).
        _owner_now_c = obs.owner_abs[_ctgt].long()
        _proj_enemy_c = (_proj_owner_c >= 0) & (_proj_owner_c != pid)
        _now_enemy_c = (_owner_now_c >= 0) & (_owner_now_c != pid)
        _owner_before_c = torch.where(
            _proj_enemy_c,
            _proj_owner_c.long(),
            torch.where(_now_enemy_c, _owner_now_c, torch.full_like(_owner_now_c, -1)),
        )                                                                         # [C]
        _enemy_owner_c = (
            (_owner_before_c >= 0)
            & (_owner_before_c < _A)
            & (_owner_before_c != pid)
            & _offensive_c
        )
        _neutral_owner_c = (_owner_before_c < 0) & _offensive_c

        _delta = torch.zeros((C, _A), dtype=dtype, device=device)
        if pid < _A:
            _delta[:, pid] = torch.where(_offensive_c, _target_prod_c, torch.zeros_like(_target_prod_c))
        if bool(_enemy_owner_c.any()):
            _delta.scatter_add_(
                1,
                _owner_before_c.clamp(0, _A - 1).view(C, 1),
                torch.where(_enemy_owner_c, -_target_prod_c, torch.zeros_like(_target_prod_c)).view(C, 1),
            )
        _prod_after = (_owner_prod.view(1, _A) + _delta).clamp(min=0.0)            # [C,A]
        _total_after = (
            _total_prod0 + torch.where(_neutral_owner_c, _target_prod_c, torch.zeros_like(_target_prod_c))
        ).clamp(min=1.0)
        _my_after = _prod_after[:, pid] if pid < _A else torch.zeros(C, dtype=dtype, device=device)
        _enemy_after = _prod_after.clone()
        if pid < _A:
            _enemy_after[:, pid] = -float("inf")
        _leader_after = _enemy_after.max(dim=1).values.clamp(min=0.0)
        _margin_after = (_my_after - _leader_after) / _total_after
        _delta_margin = _margin_after - _margin0

        _remaining = (_eta_c.new_full((C,), float(os.environ.get("PRODUCER_RACE_END", "80")) - float(cur_step)) - _eta_c).clamp(min=1.0)
        _race_value = (_delta_margin * _total_prod0 * _remaining)
        _race_value = torch.where(
            cand_valid & _offensive_c & torch.isfinite(_race_value),
            _race_value.clamp(min=0.0),
            torch.zeros_like(_race_value),
        )
        _race_weight = float(os.environ.get("PRODUCER_RACE_WEIGHT", "0.20"))
        _initial_planets = obs_tensors.get("initial_planets")
        if _initial_planets is not None:
            _initial_alive = _initial_planets[..., 0] >= 0
            _map_prod_total = float(_initial_planets[..., 6][_initial_alive].to(dtype).sum().item())
        else:
            _map_prod_total = float(prod[obs.alive].to(dtype).sum().item())
        _race_apply_c = _offensive_c
        _mp_med_low = float(os.environ.get("PRODUCER_RACE_MP_MED_LOW", "64"))
        _mp_med_high = float(os.environ.get("PRODUCER_RACE_MP_MED_HIGH", "76"))
        _mp_high = float(os.environ.get("PRODUCER_RACE_MP_HIGH", "88"))
        if _map_prod_total >= _mp_high or (_mp_med_low <= _map_prod_total < _mp_med_high):
            if cur_step < int(os.environ.get("PRODUCER_RACE_START", "30")):
                _race_apply_c = torch.zeros_like(_offensive_c, dtype=torch.bool)
        elif _mp_med_high <= _map_prod_total < _mp_high:
            if cur_step < int(os.environ.get("PRODUCER_RACE_NEUTRAL_ONLY_END", "50")):
                _race_apply_c = _race_apply_c & _neutral_owner_c
        race_rank_value = torch.where(
            cand_valid & _offensive_c,
            score + _race_weight * torch.where(_race_apply_c, _race_value, torch.zeros_like(_race_value)),
            torch.zeros_like(score),
        )

    # [v25] Iterative multi-wave greedy now lives in the framework
    # (planner_core.plan_iterative_waves) — pure mechanism (greedy select → apply →
    # rebuild garrison → multi-source-keep). The strategy half (re-score with all
    # bonuses each wave) is injected via this rescore_fn closure, so bonuses stay in
    # the shell. Behaviour is byte-identical to the old inline v19 loop.
    def _rescore_fn(_gs_iter, _abs_iter):
        _launches_new = make_launch_set(
            source_slots=cand_src,
            target_slots=cand_tgt_slot.unsqueeze(-1).expand(C, L),
            ships=cand_send, eta=cand_eta,
            valid=cand_active & cand_valid.unsqueeze(-1),
            player_id=pid, depart_turn=cand_delay_cl,
        )
        _s = score_candidates(
            _gs_iter, prod=prod, alive_by_step=_abs_iter,
            player_count=int(player_count), launches=_launches_new, player_id=pid,
            combat_mode=cand_combat_mode, prod_mode=cand_prod_mode, prod_hold_frac=cand_prod_hold_frac,
            combat_scale=cand_combat_scale,
        )
        # [v47] 同上: 前线源星禁打中立 (rescore 也要应用)
        if not os.environ.get("PRODUCER_NO_FRONTLINE_NEUTRAL_BAN"):
            _abo_r = getattr(_gs_iter, "arrivals_by_owner", None)
            if _abo_r is not None:
                _, _en_net_r = split_player_same_step_net(_abo_r, pid)
                _en_inf_p = _en_net_r[:, 1:7].sum(dim=-1)
                _is_neu_c = ~cand_is_enemy_eff & ~cand_is_def
                _src_threat_r = _en_inf_p[cand_src.clamp(0, P - 1)] > 0
                _ban = (_src_threat_r & cand_active).any(dim=-1) & _is_neu_c
                if _low_rotating_neutral_release_enabled():
                    _ban = _ban & ~_is_neu_c
                _s = torch.where(_ban, torch.full_like(_s, float("-inf")), _s)
        _s = torch.where(cand_valid, _s, torch.full_like(_s, float("-inf")))
        _s = _apply_neutral_adjustments(_s)
        _s = _apply_2p_source_risk_cost(_s)
        _s = _apply_2p_late_defense_decay(_s)
        _s = _apply_2p_big_long_uncertain_penalty(_s)
        return _apply_all_bonuses(_s)

    wave_entries, leftover, held_sources = plan_iterative_waves(
        movement=movement, obs_tensors=obs_tensors, player_id=pid, H=H, W=W,
        device=device, dtype=dtype,
        cand_src=cand_src, cand_send=cand_send, cand_angle=cand_angle, cand_eta=cand_eta,
        cand_active=cand_active, cand_tgt_slot=cand_tgt_slot, cand_tgt_short=cand_tgt_short,
        cand_is_def=cand_is_def, cand_delay=cand_delay, cand_src_prod=cand_src_prod,
        target_idx=target_idx, target_exists=target_exists,
        init_budget=obs.ships.to(dtype), init_score=score, roi_threshold=eff_roi,
        rescore_fn=_rescore_fn,
        # [v26] ROI-ratio ranking: greedy picks by net-value-PER-SHIP (score/Σships) instead
        # of absolute net value, so a fixed fleet budget captures more stars (efficient small
        # waves beat big costly ones). Clean arena vs v20: 60% (abs) → 73.3% (ROI-ratio) at
        # H=18. The fire GATE stays absolute net > roi_threshold.
        rank_by_roi=True,
        # [v27] ROI denominator = max(single-source send, capture floor): a star needing
        # convergence is ranked by the TOTAL fleet to take it, not one source's send — so
        # the planner regulates against over-committing to uncertain high-defence attacks.
        # Clean arena vs v20 (30局×3对手): 55.2% → 69.0% (+13.8pp). 零退化、全对手一致.
        cand_cost=cand_cost,
        rank_value=race_rank_value,
    )
    _attack_entry_width = int(wave_entries.valid.numel())

    # [v35] 透出**进攻波数**(不含 regroup)给滑动H用。进攻波=找到了真扩张/压制出口;
    # 只regroup(自己星间倒兵)≠出口。滑动H据此判"出口是否饱和"而非"是否发了任意一波"。
    # [v67-replay-1] Materialize the coupled rear-reinforce release above.  The
    # pre-pass only lowers A's reserve to let the attack planner spend covered
    # ships; this post-pass launches the exact B -> A cover actually needed.
    if (
        _rear_cover_src_idx is not None
        and _rear_cover_cap is not None
        and _rear_cover_can is not None
        and _rear_cover_release is not None
        and _rear_cover_eta_limit is not None
        and _reserve_full_P is not None
        and bool(wave_entries.valid.any())
    ):
        _src_slots_rear = source_idx.clamp(0, P - 1)
        _committed_P = obs.ships.to(dtype) - leftover
        _committed_A = _committed_P[_src_slots_rear].clamp(min=0.0)
        _extra_A = torch.minimum(
            (_committed_A - _drain_before_rear).clamp(min=0.0),
            _rear_cover_release,
        ).floor()
        if bool((_extra_A >= 1.0).any()):
            _rear_cover_appended = False
            _cap_left = _rear_cover_cap.clone().floor().clamp(min=0.0)
            _leftover_after_cover = leftover.clone()
            _cover_srcs: list[int] = []
            _cover_tgts: list[int] = []
            _cover_ships: list[float] = []
            _cover_angles: list[float] = []
            _cover_etas: list[float] = []
            _complete = True
            for _a in range(S):
                _need = int(_extra_A[_a].item())
                if _need <= 0:
                    continue
                _cand_b = torch.where(_rear_cover_can[:, _a] & (_cap_left >= 1.0))[0]
                if int(_cand_b.numel()) == 0:
                    _complete = False
                    break
                _order = sorted(
                    [int(x.item()) for x in _cand_b],
                    key=lambda _bi: (
                        float(_rear_cover_eta[_bi, _a].item()) if _rear_cover_eta is not None else 0.0,
                        int(_rear_cover_src_idx[_bi].item()),
                    ),
                )
                for _bi in _order:
                    _b_slot = int(_rear_cover_src_idx[_bi].item())
                    _b_surplus_now = float((_leftover_after_cover[_b_slot] - _reserve_full_P[_b_slot]).floor().clamp(min=0.0).item())
                    _take = min(
                        _need,
                        int(_cap_left[_bi].item()),
                        int(_b_surplus_now),
                    )
                    if _take <= 0:
                        continue
                    _aim_ok = None
                    while _take > 0:
                        _src_one = torch.tensor([_b_slot], dtype=torch.long, device=device)
                        _tgt_one = torch.tensor([int(_src_slots_rear[_a].item())], dtype=torch.long, device=device)
                        _ships_one = torch.tensor([float(_take)], dtype=dtype, device=device)
                        _aim_one = intercept_angle(movement, _src_one, _tgt_one, _ships_one)
                        _eta_one = float(_aim_one["eta"][0].item())
                        if bool(_aim_one["viable"][0].item()) and _eta_one < float(_rear_cover_eta_limit[_a].item()):
                            _aim_ok = _aim_one
                            break
                        _take -= 1
                    if _take <= 0 or _aim_ok is None:
                        continue
                    _cover_srcs.append(_b_slot)
                    _cover_tgts.append(int(_src_slots_rear[_a].item()))
                    _cover_ships.append(float(_take))
                    _cover_angles.append(float(_aim_ok["angle"][0].item()))
                    _cover_etas.append(float(_aim_ok["eta"][0].item()))
                    _cap_left[_bi] = _cap_left[_bi] - float(_take)
                    _leftover_after_cover[_b_slot] = (_leftover_after_cover[_b_slot] - float(_take)).clamp(min=0.0)
                    _need -= _take
                    if _need <= 0:
                        break
                if _need > 0:
                    _complete = False
                    break
            if _complete and _cover_srcs:
                _cover_src_t = torch.tensor(_cover_srcs, dtype=torch.long, device=device)
                _cover_tgt_t = torch.tensor(_cover_tgts, dtype=torch.long, device=device)
                _cover_ships_t = torch.tensor(_cover_ships, dtype=dtype, device=device)
                _cover_angle_t = torch.tensor(_cover_angles, dtype=dtype, device=device)
                _cover_eta_t = torch.tensor(_cover_etas, dtype=dtype, device=device)
                _cover_valid = torch.ones(len(_cover_srcs), dtype=torch.bool, device=device)
                cover_entries = LaunchEntries(
                    source_slots=_cover_src_t,
                    target_slots=_cover_tgt_t,
                    ships=_cover_ships_t,
                    angle=_cover_angle_t,
                    eta=_cover_eta_t,
                    valid=_cover_valid,
                )
                if bool(cover_entries.valid.any()):
                    leftover = _leftover_after_cover
                    wave_entries = concat_launch_entries([wave_entries, cover_entries])
                    _rear_cover_appended = True
            if not _rear_cover_appended:
                # Last-resort consistency guard: if the pre-pass released reserve
                # but the exact B -> A cover cannot be materialized, do not keep
                # an unsupported attack that spends A below its original reserve.
                _need_by_slot = torch.zeros(P, dtype=dtype, device=device)
                _need_by_slot.scatter_add_(0, _src_slots_rear, _extra_A.to(dtype))
                _ships_new = wave_entries.ships.clone()
                _valid_new = wave_entries.valid.clone()
                for _li in range(int(wave_entries.source_slots.shape[0]) - 1, -1, -1):
                    if not bool(_valid_new[_li].item()):
                        continue
                    _s_slot = int(wave_entries.source_slots[_li].item())
                    if _s_slot < 0 or _s_slot >= P or float(_need_by_slot[_s_slot].item()) <= 0.0:
                        continue
                    _restored = float(_ships_new[_li].item())
                    _need_by_slot[_s_slot] = (_need_by_slot[_s_slot] - _restored).clamp(min=0.0)
                    leftover[_s_slot] = (leftover[_s_slot] + _restored).clamp(max=obs.ships.to(dtype)[_s_slot])
                    _ships_new[_li] = 0.0
                    _valid_new[_li] = False
                wave_entries = LaunchEntries(
                    source_slots=wave_entries.source_slots,
                    target_slots=wave_entries.target_slots,
                    ships=_ships_new,
                    angle=wave_entries.angle,
                    eta=wave_entries.eta,
                    valid=_valid_new,
                )
    if out_stats is not None:
        _attack_valid = wave_entries.valid[:_attack_entry_width]
        if int(_attack_valid.numel()) == 0:
            out_stats["attack_waves"] = 0
        else:
            out_stats["attack_waves"] = int(_attack_valid.view(-1, L).any(dim=1).sum())

    # [v35] source_pending: 有 valid attack 候选但本回合没 fire 的源星 → 留兵等下回合, 不参与 regroup。
    # 解决"接近 fire 但暂时 ≤ 0 的候选, 兵被 regroup 抽走 → 下回合永远发不了"。env 旋钮 PRODUCER_PENDING_HOLD。
    source_pending = None
    _auto_low_pending_hold = False
    if int(player_count) == 4:
        _initial_planets_for_pending = obs_tensors.get("initial_planets")
        if _initial_planets_for_pending is not None:
            _initial_alive_for_pending = _initial_planets_for_pending[..., 0] >= 0
            _pending_initial_prod = _initial_planets_for_pending[..., 6].to(dtype)
            _pending_map_prod_total = float(_pending_initial_prod[_initial_alive_for_pending].sum().item())
            _planet_ids_pending = _initial_planets_for_pending[..., 0].long()
            _comet_ids_pending = obs_tensors.get("comet_planet_ids")
            if _comet_ids_pending is not None:
                _valid_comets_pending = _comet_ids_pending.long()
                _valid_comets_pending = _valid_comets_pending[_valid_comets_pending >= 0]
                if int(_valid_comets_pending.numel()) > 0:
                    _is_comet_pending = (
                        _planet_ids_pending.unsqueeze(-1) == _valid_comets_pending.view(1, -1)
                    ).any(dim=-1)
                else:
                    _is_comet_pending = torch.zeros_like(_initial_alive_for_pending, dtype=torch.bool)
            else:
                _is_comet_pending = torch.zeros_like(_initial_alive_for_pending, dtype=torch.bool)
            _base_planets_pending = _initial_alive_for_pending & ~_is_comet_pending
            _static_count_pending = int((_base_planets_pending & ~obs.is_orbiting).sum().item())
        else:
            _pending_map_prod_total = float(prod[obs.alive].to(dtype).sum().item())
            _static_count_pending = int((obs.alive & ~obs.is_orbiting).sum().item())
        _auto_low_pending_hold = (
            _pending_map_prod_total < float(os.environ.get("PRODUCER_RACE_MP_MED_LOW", "64"))
            and _static_count_pending >= int(os.environ.get("PRODUCER_LOW_PENDING_STATIC_COUNT_MIN", "16"))
        )
    _enable_2p_positive_pending = (
        int(player_count) == 2
        and effective_pc <= 2
        and positive_offense_candidate is not None
    )
    if os.environ.get("PRODUCER_PENDING_HOLD") or _auto_low_pending_hold or _enable_2p_positive_pending:
        _pending_candidate = cand_valid
        if _enable_2p_positive_pending:
            _pending_candidate = positive_offense_candidate
        _pending_mask = _pending_candidate.view(C, 1) & cand_active
        _cand_src_flat = cand_src[_pending_mask].reshape(-1)
        _has_cand = torch.zeros(P, dtype=torch.bool, device=device)
        if _cand_src_flat.numel() > 0:
            _has_cand.scatter_(0, _cand_src_flat.clamp(0, P - 1), True)
        # 已 fire 的源星集合
        _fired_src = torch.zeros(P, dtype=torch.bool, device=device)
        if wave_entries.valid.any():
            _fired_src.scatter_(0, wave_entries.source_slots[wave_entries.valid], True)
        # pending = 有候选但没 fire
        source_pending = _has_cand & ~_fired_src                                      # [P]
    if bool(held_sources.any()):
        source_pending = held_sources if source_pending is None else (source_pending | held_sources)
    if not bool(config.enable_regroup):
        return wave_entries
    if _opportunity_keep_P is not None:
        if _regroup_source_reserve_P is None:
            _regroup_source_reserve_P = _opportunity_keep_P
        else:
            _regroup_source_reserve_P = torch.maximum(
                _regroup_source_reserve_P.to(device=device, dtype=dtype),
                _opportunity_keep_P,
            )
    enemy_mass = cheap_enemy_pressure(obs, cache, horizon=float(K_eta), player_id=pid)
    # [v33 deficit-regroup 已证伪默认关] 把regroup送兵目标从pressure改成防守缺口(敌k可达−友k可达):
    # 逐帧(seed3)单开deficit就崩(峰值14→0星, 发122波但兵全送给守不住的前线星=白送被夺)。根因: 92%
    # 防守缺口星本来就局部劣势(对称k窗口), 往那送兵=喂给对手。**默认关(用pressure原行为)**, 仅env开。
    _regroup_signal = enemy_mass
    if _deficit_P is not None and os.environ.get("PRODUCER_DEFICIT_REGROUP"):
        _regroup_signal = _deficit_P
    # [v35] 一阶有方向性压力传染: effective_pressure[t] = max over (一跳可达 t 的友星 v ∪ {t}) of raw[v]
    # 解决 cap 放宽后"远端终点站盖过近邻中转站"的问题: 中转站 effective 等于终点站, 由 eta 罚项选近邻
    # → 链式中继自然形成。可达性用 PRODUCER_REGROUP_T (默认走 max_regroup_time=7) 一跳距离判定。
    # **传 raw 和 eff 两套**: filter 用 raw_gap (真敌方实力差防多源汇聚黑洞), score 用 eff_gap (链式中继排序)。
    _regroup_raw = _regroup_signal  # 总是传 raw, 默认下游 filter 用 eff 与之相同 (无传染时 raw=eff)
    if os.environ.get("PRODUCER_PRESSURE_PROPAGATE"):
        _T_max = float(os.environ.get("PRODUCER_REGROUP_T", str(config.max_regroup_time)))
        _spd = fleet_speed(obs.ships.clamp(min=1e-6)).to(dtype)                         # [P]
        _Tk = max(1, min(int(_T_max), cache.cross_dist.shape[0] - 1))
        _d_t = cache.cross_dist[_Tk].to(dtype)                                          # [P,P] dist(s@0, t@k)
        _reach1 = (_spd.view(P, 1) * float(_T_max)) >= _d_t                              # [s,t] s 一跳可达 t
        _eye = torch.eye(P, dtype=torch.bool, device=device)
        _mine = obs.owned & obs.alive
        _A = (_reach1 | _eye) & _mine.view(P, 1) & _mine.view(1, P)                      # [s,t] 友→友 一跳含自身
        _raw_b = torch.where(_A, _regroup_raw.view(P, 1).expand(P, P),
                             torch.full((P, P), float("-inf"), dtype=dtype, device=device))
        _eff = _raw_b.max(dim=0).values                                                  # [P] = max over s of raw[s]
        # 非我方星保留 raw(它们不参与传染, 不会被选作 dst)
        _regroup_signal = torch.where(_mine, _eff, _regroup_raw)

    _regroup_reserve = None
    if (
        not os.environ.get("PRODUCER_NO_MINKEEP")
        and not os.environ.get("PRODUCER_NO_REGROUP_RESERVE")
        and _min_keep_P is not None
    ):
        _regroup_reserve = _min_keep_P.to(device=device, dtype=dtype)
        if not os.environ.get("PRODUCER_NO_ROT_STAT_SPLIT"):
            _stat_mult = float(os.environ.get("PRODUCER_STAT_RESERVE_MULT", "1.0"))
            _rot_basis_P = _regroup_reserve
            if os.environ.get("PRODUCER_ROT_SUPPORTED_SELF_ONLY", "1") == "1" and _self_gap_P is not None:
                _rot_basis_P = _self_gap_P.to(device=device, dtype=dtype)
            _rot_mult_P = _rotating_reserve_multiplier(
                obs, cache, reserve_full_P=_rot_basis_P, pid=pid,
                K_eta=K_eta, device=device, dtype=dtype,
            )
            _regroup_reserve = torch.where(obs.is_orbiting, _rot_basis_P, _regroup_reserve)
            _regroup_reserve = torch.where(
                obs.is_orbiting, _regroup_reserve * _rot_mult_P, _regroup_reserve * _stat_mult,
            )
    if _regroup_reserve is not None:
        if _regroup_source_reserve_P is None:
            _regroup_source_reserve_P = _regroup_reserve
        else:
            _regroup_source_reserve_P = torch.maximum(
                _regroup_source_reserve_P.to(device=device, dtype=dtype),
                _regroup_reserve.to(device=device, dtype=dtype),
            )

    regroup_support_need = None
    regroup_support_value = None
    regroup_target_bias = None
    if int(player_count) == 2 and effective_pc <= 2:
        _mine_alive = obs.owned & obs.alive
        if _deficit_P is not None:
            _def_need = _deficit_P.to(device=device, dtype=dtype).clamp(min=0.0)
            regroup_support_need = torch.where(
                _mine_alive,
                _def_need,
                torch.zeros(P, dtype=dtype, device=device),
            )
            regroup_support_value = torch.where(
                _mine_alive,
                prod.to(dtype) * float(H) * 2.0,
                torch.zeros(P, dtype=dtype, device=device),
            )
        if _local_balance_reserve_P is not None:
            _reserve_need = _local_balance_reserve_P.to(device=device, dtype=dtype).clamp(min=0.0)
            _need_ratio = (_reserve_need / obs.ships.to(dtype).clamp(min=1.0)).clamp(max=1.0)
            # [v67-regroup-6] Local-balance reserve is a prepositioning hint, not
            # an action trigger. It only breaks ties among already-valid pressure,
            # staging, or concrete rescue regroup targets.
            regroup_target_bias = torch.where(
                _mine_alive,
                prod.to(dtype) * float(H) * _need_ratio,
                torch.zeros(P, dtype=dtype, device=device),
            )
    regroup_entries = _plan_regroup(
        movement=movement, obs=obs, obs_tensors=obs_tensors, garrison_status=garrison_status,
        leftover=leftover, original_ships=obs.ships.to(dtype), pressure=_regroup_signal,
        config=config, H=H, pressure_raw=_regroup_raw, source_pending=source_pending,
        staging_value=regroup_staging_value, source_hold=held_sources,
        source_reserve=_regroup_source_reserve_P,
        support_need=regroup_support_need, support_value=regroup_support_value,
        support_horizon=float(H), target_bias=regroup_target_bias,
    )
    if os.environ.get("PRODUCER_SPLIT_LOG"):
        import sys as _sys
        _aw = float(wave_entries.ships[wave_entries.valid].sum()) if bool(wave_entries.valid.any()) else 0.0
        _rw = float(regroup_entries.ships[regroup_entries.valid].sum()) if bool(regroup_entries.valid.any()) else 0.0
        _lo = float(leftover[obs.owned].sum())
        print(f"SPLIT attack={_aw:.0f} regroup={_rw:.0f} leftover={_lo:.0f}", file=_sys.stderr)

    # [v38 comet rescue 兜底] 离场前 1 回合, 我方占的 comet 如果还没作为 source 派兵 (attack +
    # regroup 都没用它), 强制全兵 launch 到最近友方星 (LB 79748581 t81 p31 16兵随 comet 离场全损)。
    # 直接不管 ETA, 引擎会让 fleet 离开 comet 星 → comet 消失时 fleet 在外面飞 → 兵保住。
    comet_rescue = _build_comet_rescue(
        obs=obs, obs_tensors=obs_tensors, cache=cache, movement=movement, pid=pid,
        wave_entries=wave_entries, regroup_entries=regroup_entries,
        device=device, dtype=dtype,
    )
    return concat_launch_entries([wave_entries, regroup_entries, comet_rescue])


def run_turn(obs_tensors: dict, *, config: ProducerLiteConfig, player_count: int, memory) -> dict:
    """Full per-turn pipeline: build movement → plan single-size waves + regroup → emit.

    ``memory`` must expose a mutable ``movement`` attribute (the rolling cache).
    """
    device = obs_tensors["planets"].device
    obs = parse_obs(obs_tensors)
    P = obs.P
    if P == 0:
        return empty_action_row(device)

    # [v32d 自愈滑动H] 在给定 H 下规划一回合。movement 缓存复用由 ensure_planet_movement 的
    # config 相等判定处理(H 不变则滚动复用, H 变则从 obs 重建——重建正确, 仅丢私有 planned-launch
    # 的跨回合记忆, 影响小)。
    def _plan_at_H(_H):
        _cfg_H = dataclasses.replace(config, horizon=_H)
        mv = ensure_planet_movement(
            obs_tensors=obs_tensors,
            expected_cfg=_movement_config(_cfg_H, player_count=int(player_count)),
            cached_movement=getattr(memory, "movement", None),
        )
        _cache = build_distance_cache(mv, max_k=_H)
        _status = mv.garrison_status(max_horizon=_H)
        _abs = mv.alive_by_step[: _H + 1]
        _st = {}
        _ent = plan_lite_waves(
            movement=mv, obs=obs, obs_tensors=obs_tensors, cache=_cache,
            garrison_status=_status, prod=mv.planet_prod,
            alive_by_step=_abs, config=_cfg_H,
            player_count=int(player_count), out_stats=_st,
        )
        return mv, _ent, int(_st.get("attack_waves", 0))

    # [v32 自愈滑动H(用户)] H 在 [LO, HI](默认[12,30]) 双向滑动, 初始 INIT(默认18=config.horizon):
    # 上一回合**发了波→H−DOWN**(回收), **发0波→H+UP**(放宽)。用完即退、自带自愈。
    # **核心机制(地图自适应)**: 旋转星(位置随轨道变)需要**短H**(投影久了未来位置算错→碎片化打空);
    # 静止星需要**长H**(看远、敢规划远期扩张)。宽区间[12,30]让H两端都够得着→顺利扩张时降到12(聚焦
    # 近处, 救rotating), 死锁时爬到30(找远扩张步, 帮static)。窄区间锁一端只能帮一类地图。
    # **128-seed panel A/B(vs v31): LO12_HI30_I18 = 71.9%(rot64.6/stat93.8), 远胜窄区间(LO18_HI24
    # 59.4/stat75但rot仅54, LO16_HI24 53.1)。** 五旋钮均 env 可调; PRODUCER_NO_HRESCUE 关闭回退纯v31。
    _LO = int(os.environ.get("PRODUCER_HRESCUE_LO", "12"))                        # 下限(默认12)
    _HI = int(os.environ.get("PRODUCER_HRESCUE_HI", "30"))                        # 上限(默认30)
    _INIT = int(os.environ.get("PRODUCER_HRESCUE_INIT", str(int(config.horizon))))  # 开局初始H(默认18)
    _up = int(os.environ.get("PRODUCER_HRESCUE_UP", "1"))                         # 发0波时 H 上调步长
    _down = int(os.environ.get("PRODUCER_HRESCUE_DOWN", "1"))                     # 发波时 H 回收步长
    if os.environ.get("PRODUCER_NO_HRESCUE"):
        _LO = _HI = _INIT = int(config.horizon)
    _dynH = getattr(memory, "dyn_H", None)
    _dynH = _INIT if _dynH is None else int(_dynH)
    _dynH = max(_LO, min(_HI, _dynH))
    movement, entries, _atk_waves = _plan_at_H(_dynH)
    # 下一回合的 H: 出口饱和→−DOWN(回收), 否则→+UP(放宽), clamp 到 [LO, HI]。
    # [v35] 把"回收"信号从"发了任意一波"(entries.valid.any(), **含regroup**)改成
    # "**进攻波**数 ≥ SAT"。理由(seed2逐帧+3局量化): regroup(自己星间倒兵)不是扩张出口,
    # 22%回合只regroup无进攻却被旧逻辑误判fired→H−1→视野收紧→兵囤着没出口。进攻波分布
    # 0波74%/1波23%/2波3% → SAT=1 恰好分"有真扩张(回收) vs 无扩张(放宽找出口)"。
    # 默认 SAT 未设 → 完全等于 v32(entries.valid.any), 安全; SAT=N opt-in 后 A/B。
    _sat_env = os.environ.get("PRODUCER_HRESCUE_SAT")
    memory.movement = movement
    entries = disambiguate_duplicate_launches(entries)
    launches = infer_planned_launches_from_entries(
        obs_tensors=obs_tensors, movement=movement, entries=entries, player_id=int(obs.player_id),
    )
    physical_hit_ok = entries.valid & launches.valid & (launches.target_slots == entries.target_slots)
    if bool((entries.valid & ~physical_hit_ok).any()):
        # Final guard: scoring is tied to entries.target_slots.  If the exact
        # swept physics says the emitted angle misses or hits a different planet,
        # do not launch a fleet scored for another outcome.
        entries = LaunchEntries(
            source_slots=entries.source_slots,
            target_slots=entries.target_slots,
            ships=torch.where(physical_hit_ok, entries.ships, torch.zeros_like(entries.ships)),
            angle=entries.angle,
            eta=entries.eta,
            valid=physical_hit_ok,
        )
        launches = infer_planned_launches_from_entries(
            obs_tensors=obs_tensors, movement=movement, entries=entries, player_id=int(obs.player_id),
        )
    if _sat_env is None:
        _recover = bool(entries.valid.any())
    else:
        _recover = bool(entries.valid.any()) and (_atk_waves >= int(_sat_env))
    memory.dyn_H = max(_LO, min(_HI, _dynH + (-_down if _recover else _up)))
    apply_private_planned_launches(
        movement=movement, launches=launches, owner_id=int(obs.player_id),
        obs_tensors=obs_tensors,
    )
    planet_ids = obs_tensors["planets"][..., 0].long()
    return entries_to_sparse_payload(entries, planet_ids=planet_ids)


# 4P FFA preset — only the knobs that differ from the 2P default.
CONFIG_4P = dataclasses.replace(
    ProducerLiteConfig(),
    # [v28] horizon 13→18: the old 13 (v0-era, pre-收益率排序/增援muster) starved 4P mid-game
    # — produced window too small → mid targets failed ROI → expansion stalled at ~3 stars
    # while opponents snowballed to 11+ (逐回合: step30 持平→step120 落后9星). With v26/v27's
    # ROI-ratio ranking + reinforcement modelling, H=18 (same as 2P) makes 4P expand properly.
    # Clean arena vs v0/v10/v20 (24局): 1st 12%→33%, avg rank 1.88→1.67. (H=22 略降 38%@16局/
    # 1.62; max_sources 6→12 反降 33%→25%, kept at 6.)
    horizon=18,
    max_sources_per_lane=6,
    max_defensive_targets=2,
    max_regroup_time=6.0,
    max_regroup_targets_per_source=8,
)


def _config_for(player_count: int) -> ProducerLiteConfig:
    return CONFIG_4P if int(player_count) >= 4 else ProducerLiteConfig()


class ProducerLiteMemory:
    def __init__(self) -> None:
        self.movement = None
        self.cached_player_count: int | None = None
        self.last_sparse_action_row: dict | None = None
        self.dyn_H: int | None = None           # [v32d] 自愈滑动 horizon(发波−1/0波+1, 区间[baseH,HI])

    def reset(self) -> None:
        self.movement = None
        self.cached_player_count = None
        self.last_sparse_action_row = None
        self.dyn_H = None


class ProducerLiteRuntime:
    def __init__(self, memory: ProducerLiteMemory | None = None) -> None:
        self.memory = memory if memory is not None else ProducerLiteMemory()

    def reset(self) -> None:
        self.memory.reset()

    def tensor_action(self, obs_tensors: dict):
        mem = self.memory
        if bool((obs_tensors["step"] == 0).all()):
            mem.reset()
        if mem.cached_player_count is None:
            mem.cached_player_count = largest_initial_player_count(obs_tensors)
        config = _config_for(mem.cached_player_count)
        row = run_turn(
            obs_tensors, config=config,
            player_count=int(mem.cached_player_count), memory=mem,
        )
        mem.last_sparse_action_row = row
        return row


_RUNTIME = ProducerLiteRuntime()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _v46_obs_matches_initial_frame(obs: dict) -> bool:
    """Best-effort new-episode detector for the obs.step=None fallback."""
    planets = obs.get("planets")
    initial = obs.get("initial_planets")
    fleets = obs.get("fleets", [])
    if not isinstance(planets, list) or not isinstance(initial, list):
        return False
    if len(planets) != len(initial):
        return False
    if isinstance(fleets, list):
        for fleet in fleets:
            if len(fleet) >= 1 and int(fleet[0]) >= 0:
                return False
    else:
        return False
    owned_counts: dict[int, int] = {}
    for cur, init in zip(planets, initial):
        if len(cur) < 7 or len(init) < 7:
            return False
        if int(cur[0]) != int(init[0]):
            return False
        for idx in (2, 3, 4, 6):
            if abs(float(cur[idx]) - float(init[idx])) > 1e-5:
                return False
        owner = int(cur[1])
        if owner >= 0:
            owned_counts[owner] = owned_counts.get(owner, 0) + 1
            if int(init[1]) >= 0:
                return False
            if abs(float(cur[5]) - 10.0) > 1e-5:
                return False
        else:
            if int(init[1]) != owner:
                return False
            if abs(float(cur[5]) - float(init[5])) > 1e-5:
                return False
    if not owned_counts:
        return False
    owners = sorted(owned_counts)
    player_count = len(owners)
    return player_count in (2, 4) and owners == list(range(player_count)) and all(
        count == 1 for count in owned_counts.values()
    )


def _v46_missing_step_fallback(obs: dict, player_id: int) -> int:
    """Fallback step counter for Kaggle obs.step=None, scoped per player."""
    global _V46_STEP_COUNTERS
    try:
        counters = _V46_STEP_COUNTERS
    except NameError:
        counters = {}
        _V46_STEP_COUNTERS = counters
    pid = int(player_id)
    if _v46_obs_matches_initial_frame(obs):
        counters[pid] = 0
    step = int(counters.get(pid, 0))
    counters[pid] = step + 1
    return step


def agent(obs):
    """Single-observation entry point for local play and Kaggle."""
    player = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    player_id = int(player)
    # [v46] kaggle_environments bug: 非 P0 玩家 obs.step = None (实测+replay 验证).
    # 导致 movement.x 用 step=0 算 phase, 把 fleet 落点算到错误位置 → fleet_buckets 漏记
    # → garrison_status 投影看不到敌方反扑 → score 让我"前线派兵打中立, 转头被夺".
    # replay 80046504 t27: P1 派 30 兵 from p31 打 p18, 而敌 71 兵正在飞向 p31.
    # 修法: 用 module-level counter 累加 step (每次 agent 调用 +1, reset 时归零).
    # 仅当 obs.step is None 时启用 (如果 obs.step 有效, 优先用 obs 给的真实 step).
    if isinstance(obs, dict) and obs.get("step") is None:
        obs = dict(obs)  # 浅 copy 避免修改 caller 的 dict
        obs["step"] = _v46_missing_step_fallback(obs, player_id)
    obs_tensors = single_obs_to_tensor(obs, player_id=player_id)
    with torch.no_grad():
        sparse_row = _RUNTIME.tensor_action(obs_tensors)
    return sparse_action_row_to_moves(sparse_row, obs, player_id=player_id)


# [v46] step counters (对 obs.step=None 的 player 兜底). 按 player 分开维护, 并在
# 看到初始帧时 reset, 避免同一进程顺序跑多局或复用同模块时 step 漂移。
_V46_STEP_COUNTERS: dict[int, int] = {}
