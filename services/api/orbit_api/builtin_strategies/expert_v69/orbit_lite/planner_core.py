"""Flow-diff scored planner core: candidate scoring, shortlists, aim, selection.

Pure, tensor-only planning helpers for one game: the competitive net-ship-delta
scorer, target/source shortlists, capture-floor sizing, the strict-superset
reachability gate, the device-stable greedy selector, the hold-reserve cap
``safe_drain``, and the pressure-gradient regrouper.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import torch
from torch import Tensor

from .garrison_launch import GarrisonFlowDiff, LaunchSet, sparse_launch_flow_delta
from .movement import PlanetGarrisonStatus, PlanetMovement
from .geometry import fleet_speed
from .intercept_aim import intercept_angle
from .movement_aiming import LAUNCH_SURFACE_OFFSET, TARGET_HIT_SURFACE_OFFSET
from .movement_step import (
    LaunchEntries,
    apply_private_planned_launches,
    concat_launch_entries,
    disambiguate_duplicate_launches,
    infer_planned_launches_from_entries,
)
from .distance_cache import min_distance_to_targets




def reachable_mass(obs, cache, *, horizon: float, player_id: int, side: str) -> Tensor:
    """Distance-decayed reachable ship mass per planet — ``[P]``.

    For each planet ``t``, sums a distance-decayed share of every source's current
    garrison that could straight-line reach ``t`` within ``horizon`` turns (step-0
    centre distance ``cross_dist[0]``; decay ``(1 − d/(speed·H))₊``, nearer = heavier).
    ``side='enemy'`` sums live enemy sources (the regroup-gradient pressure proxy);
    ``side='friendly'`` sums live own sources (strategic-balance support). Pure
    arithmetic on cached tensors; ignores orbital drift, in-flight fleets, production
    in flight. Moved from the agent shell (was cheap_enemy_pressure /
    _friendly_reachable_mass) — pure mechanism, no strategy.
    """
    P = int(obs.P)
    device = obs.device
    dtype = obs.ships.dtype
    if P == 0:
        return torch.zeros(P, dtype=dtype, device=device)
    d0 = cache.cross_dist[0].to(dtype)                                   # [src, tgt]
    ships = obs.ships.to(dtype)
    speeds = fleet_speed(ships.clamp(min=1e-6))                          # [P]
    reach_dist = (speeds.view(P, 1) * float(horizon)).clamp(min=1e-6)    # [src, 1]
    if side == "friendly":
        src_sel = obs.alive & (obs.owner_abs == int(player_id))
    else:
        src_sel = obs.alive & (obs.owner_abs >= 0) & (obs.owner_abs != int(player_id))
    eye = torch.eye(P, device=device, dtype=torch.bool)
    valid = src_sel.view(P, 1) & obs.alive.view(1, P) & ~eye             # [src, tgt]
    decay = (1.0 - d0 / reach_dist).clamp(min=0.0)
    contrib = torch.where(valid, ships.view(P, 1) * decay, torch.zeros_like(decay))
    return contrib.sum(dim=0)                                            # [P]


@dataclass(frozen=True)
class AttackCandidates:
    """Objective per-candidate attack table produced by ``build_attack_candidates``.

    One candidate per ``(source, target, delay)``; contributor axis ``L == 1``. The
    shell layers strategy (bonuses / opportunity-cost discount) on top using these
    objective fields — the framework only computes the physics (reachable fleet,
    aim, arrival, capture floor, multi-source admission)."""
    cand_src: Tensor          # [C, L]
    cand_send: Tensor         # [C, L]
    cand_angle: Tensor        # [C, L]
    cand_eta: Tensor          # [C, L]
    cand_active: Tensor       # [C, L]
    cand_valid: Tensor        # [C]
    cand_tgt_slot: Tensor     # [C]
    cand_tgt_short: Tensor    # [C]
    cand_is_def: Tensor       # [C]
    cand_delay: Tensor        # [C]
    cand_src_prod: Tensor     # [C, L]
    cand_hold: Tensor         # [C] deterministic预期持有回合(占领后能守多久)
    cand_cost: Tensor         # [C] 占下该星真正要投入的兵力 = max(单源发兵, 到达时capture floor)
    C: int
    L: int
    D: int


def split_player_same_step_net(arrivals_by_owner: Tensor, player_id: int) -> tuple[Tensor, Tensor]:
    """Net same-step arrival survivor split into player vs non-player ships.

    ``arrivals_by_owner`` is ``[..., A]`` per-owner buckets for one target/turn.
    The engine resolves simultaneous fleet arrivals by keeping only ``top1-top2``
    over owners (ties annihilate). For 3P/4P planning, summing all non-player
    buckets is physically wrong because opponents also fight each other.
    """
    A = int(arrivals_by_owner.shape[-1])
    if A >= 2:
        top2 = arrivals_by_owner.topk(k=2, dim=-1)
        top_ships = top2.values[..., 0]
        second_ships = top2.values[..., 1]
        top_owner = top2.indices[..., 0].to(dtype=torch.long)
    else:
        top_ships, top_owner = arrivals_by_owner.max(dim=-1)
        second_ships = torch.zeros_like(top_ships)
        top_owner = top_owner.to(dtype=torch.long)
    tied = top_ships == second_ships
    survivor = torch.where(
        tied,
        torch.zeros_like(top_ships),
        (top_ships - second_ships).clamp(min=0.0),
    )
    friendly = torch.where(
        top_owner == int(player_id),
        survivor,
        torch.zeros_like(survivor),
    )
    enemy = torch.where(
        (top_owner >= 0) & (top_owner != int(player_id)),
        survivor,
        torch.zeros_like(survivor),
    )
    return friendly, enemy


def _side_arrival_turns(obs, cache, target_idx, *, src_mask, K_eta, device, dtype):
    """For each shortlist target T, each source star's arrival turn at T assuming EVERY
    selected source departs NOW, dynamic cross-time distance. Returns
    ``(arr [T,M], ships [M], dist0 [T,M])``: arr[t,m] = earliest k in 1..K_eta with
    fleet_speed(ships_m)·k >= dist(m@0, T@k); K_eta+1 if never reaches. dist0 is the
    step-0 centre distance from source m to target t (for distance-decay weighting).
    ``src_mask`` [P] selects which planets count as sources (enemy or friendly). Pure 物理时序."""
    P = int(obs.P)
    M_idx = src_mask.nonzero(as_tuple=False).reshape(-1)                                # [M]
    M = int(M_idx.numel()); T = int(target_idx.numel())
    if M == 0 or T == 0:
        return (torch.full((T, max(M, 0)), float(K_eta + 1), device=device, dtype=dtype),
                torch.zeros(max(M, 0), device=device, dtype=dtype),
                torch.full((T, max(M, 0)), 1e9, device=device, dtype=dtype))
    m_ships = obs.ships[M_idx].to(dtype)                                                # [M]
    m_speed = fleet_speed(m_ships.clamp(min=1e-6)).to(dtype)                            # [M]
    tgt = target_idx.clamp(0, P - 1)
    Kmax = min(int(K_eta), cache.cross_dist.shape[0] - 1)
    ks = torch.arange(1, Kmax + 1, device=device, dtype=dtype)                          # [Kk]
    cross = cache.cross_dist[1:Kmax + 1][:, M_idx][:, :, tgt].to(dtype)                 # [Kk,M,T]
    reach = m_speed.view(1, M, 1) * ks.view(-1, 1, 1)                                   # [Kk,M,T]
    can = reach >= cross
    big = float(K_eta + 1)
    kgrid = ks.view(-1, 1, 1).expand(-1, M, T)
    arr_mt = torch.where(can, kgrid, torch.full_like(kgrid, big)).amin(dim=0)           # [M,T]
    dist0 = cache.cross_dist[0][M_idx][:, tgt].to(dtype)                                # [M,T]
    return arr_mt.transpose(0, 1).contiguous(), m_ships, dist0.transpose(0, 1).contiguous()  # [T,M],[M],[T,M]


def _enemy_arrival_turns(obs, cache, target_idx, player_id, *, K_eta, device, dtype):
    """Enemy-side wrapper of ``_side_arrival_turns``. Returns ``(arr [T,E], ships [E], dist0 [T,E])``."""
    enemy_mask = obs.alive & (obs.owner_abs >= 0) & (obs.owner_abs != int(player_id))  # [P]
    return _side_arrival_turns(obs, cache, target_idx, src_mask=enemy_mask, K_eta=K_eta, device=device, dtype=dtype)


def _side_arrival_turns_per_k(obs, cache, target_idx, *, M_idx, ships_MK, K_eta, device, dtype):
    """[v41] Per-(my_turn) arrival turn refinement: arr[T, M, k] using ships at e_send_time.

    ``ships_MK`` [M, K] = each source m's ships at the frame it would depart to land on T at
    my turn k. Speed scales with that ships value (fleet_speed monotone increasing). Returns
    ``arr_TMK[T, M, K]``: earliest r ∈ [1, K_eta] with fleet_speed(ships_MK[m,k])·r ≥
    cross_dist[r, m, T]; K_eta+1 if never. Used for second-iteration refinement of muster
    schedules (用户 spec: 旋转地图飞行时距离/速度都在变, 用 e 派出帧的兵算速度更准).
    """
    M = int(M_idx.numel()); T = int(target_idx.numel())
    if M == 0 or T == 0:
        return torch.full((T, max(M, 0), K_eta), float(K_eta + 1), device=device, dtype=dtype)
    tgt = target_idx.clamp(0, int(obs.P) - 1)
    Kmax = min(int(K_eta), cache.cross_dist.shape[0] - 1)
    ks = torch.arange(1, Kmax + 1, device=device, dtype=dtype)                              # [Kk]
    cross = cache.cross_dist[1:Kmax + 1][:, M_idx][:, :, tgt].to(dtype)                     # [Kk, M, T]
    spd_MK = fleet_speed(ships_MK.clamp(min=1e-6)).to(dtype)                                # [M, K]
    # reach[r, m, t, k] = spd_MK[m, k] · r, compare with cross[r, m, t]
    # ↑ broadcast: [Kk, M, 1, 1] · [1, 1, 1, K]
    reach = spd_MK.view(1, M, 1, K_eta) * ks.view(-1, 1, 1, 1)                              # [Kk, M, 1, K]
    can = reach >= cross.view(Kmax, M, T, 1)                                                # [Kk, M, T, K]
    big = float(K_eta + 1)
    kgrid = ks.view(-1, 1, 1, 1).expand(-1, M, T, K_eta)
    arr_MTK = torch.where(can, kgrid, torch.full_like(kgrid, big)).amin(dim=0)              # [M, T, K]
    return arr_MTK.permute(1, 0, 2).contiguous()                                            # [T, M, K]


def _dist_send_fly_4d(movement, src_idx, tgt_idx, *, e_send_idx, K_eta, device, dtype):
    """[v42] 派兵帧地图距离: dist[T, E, K, R] = dist(e@e_send_time, T@(e_send_time + r)).

    Args:
        movement: PlanetMovement (含 .x [H+1, P], .y [H+1, P]).
        src_idx [E]: 敌/友星全局 id.
        tgt_idx [T]: 目标星全局 id.
        e_send_idx [T, E, K]: 每个 (T, e, my_arrival_k) 对应的 e 派出帧 (long, 已 clamp).
        K_eta: my arrival horizon.

    Returns:
        d_TEKR [T, E, K, R=K_eta]: 4D 距离张量, dist 用 e@e_send_time, T@(e_send_time + r).
    """
    H_axis = int(movement.x.shape[0])
    T = int(tgt_idx.numel()); E = int(src_idx.numel())
    R = int(K_eta)                                                                        # flight horizon
    K_my = int(e_send_idx.shape[-1])                                                      # my arrival turn axis (= K_eta usually)
    x_full = movement.x.to(dtype).to(device)                                              # [H+1, P]
    y_full = movement.y.to(dtype).to(device)
    # 索引: e@e_send_time -> ex[t,e,k] = x_full[e_send_idx[t,e,k], src_idx[e]]
    e_idx_TEK = src_idx.view(1, E, 1).expand(T, E, K_my)                                  # [T, E, K_my]
    ex_TEK = x_full[e_send_idx, e_idx_TEK]                                                # [T, E, K_my]
    ey_TEK = y_full[e_send_idx, e_idx_TEK]                                                # [T, E, K_my]

    # T@(e_send_time + r) 位置: 对每个 r ∈ [1..R] 单独算
    rs = torch.arange(1, R + 1, device=device, dtype=torch.long)                          # [R]
    # tgt_step[T, E, K_my, R] = e_send_idx + r
    tgt_step_TEKR = (e_send_idx.view(T, E, K_my, 1) + rs.view(1, 1, 1, R)).clamp(0, H_axis - 1)
    tgt_idx_TEKR = tgt_idx.view(T, 1, 1, 1).expand(T, E, K_my, R)                          # [T, E, K_my, R]
    tx_TEKR = x_full[tgt_step_TEKR, tgt_idx_TEKR]                                          # [T, E, K_my, R]
    ty_TEKR = y_full[tgt_step_TEKR, tgt_idx_TEKR]                                          # [T, E, K_my, R]

    dx = tx_TEKR - ex_TEK.view(T, E, K_my, 1)
    dy = ty_TEKR - ey_TEK.view(T, E, K_my, 1)
    d_TEKR = torch.sqrt(dx * dx + dy * dy + 1e-12)                                         # [T, E, K_my, R]
    return d_TEKR


def _exact_reinforcement_schedule_from_future_departures(
    *,
    movement,
    garrison_status,
    src_idx: Tensor,
    target_idx: Tensor,
    player_id: int,
    K_eta: int,
    device,
    dtype,
    owner_mode: str,
) -> Tensor:
    """Cumulative reinforcement schedule using future departure frames exactly.

    For each target deadline ``k`` and source ``s``, admit the largest projected
    garrison from any departure frame ``q < k`` that can contact the target on
    any arrival frame ``a <= k``.  This fixes the one-step fixed-point blind spot
    where a source with too few ships *now* is marked unreachable forever even
    though it can wait, produce, become faster, and still arrive before ``k``.
    """
    T = int(target_idx.numel())
    E = int(src_idx.numel())
    K = int(K_eta)
    sched = torch.zeros(T, K, device=device, dtype=dtype)
    if movement is None or garrison_status is None or T == 0 or E == 0 or K <= 0:
        return sched

    H_axis = int(movement.x.shape[0])
    status_H = int(garrison_status.ships.shape[-1])
    K = max(0, min(K, H_axis - 1, status_H - 1))
    if K <= 0:
        return sched

    P = int(movement.P)
    src = src_idx.to(device=device, dtype=torch.long).clamp(0, max(P - 1, 0))
    tgt = target_idx.to(device=device, dtype=torch.long).clamp(0, max(P - 1, 0))

    # q = departure frame in [0, K-1]; a = arrival/deadline frame in [1, K].
    q_steps_l = torch.arange(0, K, device=device, dtype=torch.long)
    a_steps_l = torch.arange(1, K + 1, device=device, dtype=torch.long)
    q_steps = q_steps_l.to(dtype=dtype)
    a_steps = a_steps_l.to(dtype=dtype)
    flight = a_steps.view(1, K) - q_steps.view(K, 1)                              # [Q,A]
    valid_flight = flight > 0.0

    # q is the observation/action frame after waiting q full turns.  The engine
    # processes launches before production/movement/combat in that frame, so the
    # source state available to launch is the post-combat state carried into the
    # frame, not that frame's pre-combat-after-production snapshot.
    ships_EQ = garrison_status.ships[src][:, :K].to(dtype)                        # [E,Q]
    owner_EQ = garrison_status.owner[src][:, :K]                                  # [E,Q]
    if owner_mode == "friendly":
        owner_ok_EQ = owner_EQ == int(player_id)
    else:
        owner_ok_EQ = (owner_EQ >= 0) & (owner_EQ != int(player_id))
    speed_EQ = fleet_speed(ships_EQ.clamp(min=1e-6)).to(dtype)                    # [E,Q]

    src_x_EQ = movement.x[:K, src].transpose(0, 1).to(dtype)                      # [E,Q]
    src_y_EQ = movement.y[:K, src].transpose(0, 1).to(dtype)
    tgt_x_TA = movement.x[1 : K + 1, tgt].transpose(0, 1).to(dtype)               # [T,A]
    tgt_y_TA = movement.y[1 : K + 1, tgt].transpose(0, 1).to(dtype)
    dx = tgt_x_TA[:, None, None, :] - src_x_EQ[None, :, :, None]                  # [T,E,Q,A]
    dy = tgt_y_TA[:, None, None, :] - src_y_EQ[None, :, :, None]
    center_dist = torch.sqrt((dx * dx + dy * dy).clamp(min=0.0))
    gap = (
        movement.radii[src].to(dtype).view(1, E, 1, 1)
        + LAUNCH_SURFACE_OFFSET
        + movement.radii[tgt].to(dtype).view(T, 1, 1, 1)
        + TARGET_HIT_SURFACE_OFFSET
    )
    dist = (center_dist - gap).clamp(min=0.0)

    reach = (
        speed_EQ[None, :, :, None] * flight.view(1, 1, K, K)
        >= dist
    ) & valid_flight.view(1, 1, K, K)
    if owner_mode == "friendly":
        # Friendly reinforcement is used as a credit in hold(x).  A distance-only
        # screen can count support that would actually die in the sun, go OOB, or
        # hit another planet first.  That makes attacks look holdable when the
        # engine and the main launch aimer both reject the supporting route.
        # Enemy reinforcement stays distance-only here because its overestimate is
        # conservative for capture/hold; only the friendly credit is unsafe.
        phys_reach = torch.zeros(T, E, K, K, dtype=torch.bool, device=device)
        src_grid = src.view(E, 1).expand(E, T)
        tgt_grid = tgt.view(1, T).expand(E, T)
        for q in range(K):
            active_q = owner_ok_EQ[:, q].view(E, 1).expand(E, T) & (
                src_grid != tgt_grid
            )
            if not bool(active_q.any()):
                continue
            ships_q = ships_EQ[:, q].view(E, 1).expand(E, T)
            aim_q = intercept_angle(
                movement, src_grid, tgt_grid, ships_q,
                launch_turn=int(q), active=active_q,
            )
            eta_q = aim_q["eta"].to(dtype)
            viable_q = aim_q["viable"] & torch.isfinite(eta_q)
            if not bool(viable_q.any()):
                continue
            flight_eta = eta_q.transpose(0, 1)                                  # [T,E]
            viable_te = viable_q.transpose(0, 1)                                # [T,E]
            deadline = q_steps[q] + flight_eta                                  # absolute arrival turn
            can_deadline = deadline.unsqueeze(-1) <= a_steps.view(1, 1, K)
            phys_reach[:, :, q, :] = viable_te.unsqueeze(-1) & can_deadline
        reach = reach & phys_reach
    # Deadline axis: if a source can arrive on any frame a <= k, it contributes
    # to the cumulative schedule for deadline k.
    reach_by_deadline = reach.cummax(dim=-1).values                               # [T,E,Q,K]
    not_self = (src.view(1, E, 1, 1) != tgt.view(T, 1, 1, 1))
    contrib = torch.where(
        reach_by_deadline & owner_ok_EQ.view(1, E, K, 1) & not_self,
        ships_EQ.view(1, E, K, 1),
        torch.zeros((), dtype=dtype, device=device),
    )
    per_source = contrib.max(dim=2).values                                        # [T,E,K]
    sched[:, :K] = per_source.sum(dim=1)
    return sched


def enemy_reinforcement_schedule(obs, cache, target_idx, prod, player_id, *, K_eta, device, dtype,
                                 garrison_status=None, movement=None):
    """Cumulative worst-case enemy REINFORCEMENT vs my arrival turn — ``[T, K_eta]``.

    ``sched[T, k]`` = total enemy ships defending target T if MY fleet arrives on turn
    ``k`` (1..K_eta). Each enemy star ``e`` reaches T on turn ``arr_e`` (dynamic
    cross-time distance), so to reach T by turn ``k`` it must depart at ``e_send_time
    = k − arr_e``. The force e can muster at that departure time is **the do-nothing
    projection garrison at that frame** — ``garrison_status.ships[e, e_send_time]`` —
    which auto-encodes (a) e's current garrison, (b) e's production accumulated to
    e_send_time, AND (c) all in-flight enemy fleets that land on e by e_send_time
    (post-combat, so owner changes are respected — if e flips to me by e_send_time it
    contributes 0). 用户 spec: "敌方在途到 e 后 e 中转打 T,公式必须算上"。

    Falls back to the legacy formula ``g_e + (k − arr_e)·prod_e`` if ``garrison_status``
    is not provided (kept for backwards compat with sibling agents that call this).

    Two-phase use: index at my eta → capture_floor defenders (arrives before me); the
    post-eta growth races my garrison in hold(x).
    """
    P = int(obs.P)
    T = int(target_idx.numel())
    sched = torch.zeros(T, K_eta, device=device, dtype=dtype)
    if T == 0:
        return sched
    if garrison_status is not None and movement is not None:
        # Source eligibility is checked at the future departure frame inside the
        # exact schedule. Include every live non-target planet here so a neutral
        # (or our) planet that the do-nothing projection flips to enemy before it
        # can depart is counted as a possible enemy relay.
        E_idx = obs.alive.nonzero(as_tuple=False).reshape(-1)
        return _exact_reinforcement_schedule_from_future_departures(
            movement=movement,
            garrison_status=garrison_status,
            src_idx=E_idx,
            target_idx=target_idx,
            player_id=int(player_id),
            K_eta=K_eta,
            device=device,
            dtype=dtype,
            owner_mode="enemy",
        )
    arr_TE, e_ships_E, _d0 = _enemy_arrival_turns(obs, cache, target_idx, player_id, K_eta=K_eta, device=device, dtype=dtype)  # [T,E],[E]
    E = int(e_ships_E.numel())
    if E == 0 or T == 0:
        return sched
    enemy_mask = obs.alive & (obs.owner_abs >= 0) & (obs.owner_abs != int(player_id))
    E_idx = enemy_mask.nonzero(as_tuple=False).reshape(-1)
    arr = arr_TE                                                                        # [T,E] enemy arrival turn
    ks = torch.arange(1, K_eta + 1, device=device, dtype=dtype)                         # [K] my arrival turn
    arr_e = arr.view(T, E, 1)                                                           # [T,E,1]
    kk = ks.view(1, 1, K_eta)                                                           # [1,1,K]
    arrived_by_k = arr_e <= kk                                                          # [T,E,K] enemy e in by my turn k
    # [v41 fix] 排除 e == T (目标自己): 否则 cross_dist[r,e,e]=0, arr=1, 把 T 的 do-nothing 投影
    # garrison 当成"e 派来的援军"双计 (T 的 garrison 已经在 capture_floor.defenders 里).
    not_self = (E_idx.view(1, E, 1) != target_idx.view(T, 1, 1))                        # [T,E,1]
    arrived_by_k = arrived_by_k & not_self                                              # [T,E,K]

    if garrison_status is not None:
        # [v40] e 派出时刻 e_send_time = k − arr_e (clamp 到 [0, H_axis-1])
        ships_e = garrison_status.ships                                                 # [P, H+1]
        owner_e = garrison_status.owner                                                 # [P, H+1]
        H_axis = int(ships_e.shape[-1])                                                 # H+1 帧 (k=0..H)
        e_send_time = (kk - arr_e).clamp(min=0.0, max=float(H_axis - 1))                # [T,E,K] float
        e_send_idx = e_send_time.long()                                                 # [T,E,K]
        ships_E = ships_e[E_idx].to(dtype)                                              # [E, H+1]
        owner_E = owner_e[E_idx]                                                        # [E, H+1]
        ships_TEK = ships_E.view(1, E, H_axis).expand(T, E, H_axis).gather(-1, e_send_idx)  # [T,E,K]
        owner_TEK = owner_E.view(1, E, H_axis).expand(T, E, H_axis).gather(-1, e_send_idx)  # [T,E,K]

        # [v41] 不动点迭代 1 轮: arr_0 用当前帧速度 → e_send_time_0 → 取那帧 ships → 重算 arr_1
        # 用 e 派出帧实际兵数算速度(fleet_speed 单调递增, 兵多飞快). e_send_time 也随之更新.
        # 旋转地图: 飞行途中目标也在动 (cross_dist[r] 已含), 这里补 source 速度精确化.
        # 用 e 派出帧的 ships 重算速度 (per-(M, k))
        ships_EK_iter = ships_TEK[0]   # [E, K]  — T 维 broadcast 不影响 ships 值, 取 T=0 即可
        # NOTE: ships_TEK 的 T 维实际只是广播复制了 ships_E 的值 (e_send_idx 不依赖 T 时如此)
        # 但 e_send_idx 依赖 T (因为 arr_e=arr_TE 依赖 T), 所以 T 维真实有差异。
        # 退而用平均值/向量化: 直接用每个 (T,E,K) 的 e_send_idx 取 ships, 已经是 ships_TEK
        # 这里 ships_TEK 就是每个 (T, E, K) 的 e 派出帧兵, 直接用它算速度
        spd_TEK = fleet_speed(ships_TEK.clamp(min=1e-6)).to(dtype)                       # [T, E, K]
        # [v42] 派兵帧地图距离: dist(e@e_send_time, T@(e_send_time+r)) 取代 dist(e@0, T@r).
        # 旋转地图: e 不在派兵帧 0 派出, 实际在 e_send_time 派出, 那时 e 和 T 都已转动.
        Kmax_iter = min(int(K_eta), int(movement.x.shape[0]) - 1) if movement is not None else min(int(K_eta), cache.cross_dist.shape[0] - 1)
        ks_iter = torch.arange(1, Kmax_iter + 1, device=device, dtype=dtype)             # [Kk]
        if movement is not None:
            # 4D 距离 [T, E, K, R=Kmax_iter]
            d_TEKR = _dist_send_fly_4d(movement, src_idx=E_idx, tgt_idx=target_idx,
                                       e_send_idx=e_send_idx, K_eta=Kmax_iter,
                                       device=device, dtype=dtype)                       # [T,E,K,R]
            # reach[T, E, K, R] = spd[T, E, K] · r
            reach_TEKR = spd_TEK.view(T, E, K_eta, 1) * ks_iter.view(1, 1, 1, Kmax_iter)  # [T,E,K,R]
            can_TEKR = reach_TEKR >= d_TEKR                                              # [T,E,K,R]
            big_iter = float(K_eta + 1)
            kgrid_TEKR = ks_iter.view(1, 1, 1, Kmax_iter).expand(T, E, K_eta, Kmax_iter)
            arr_TEK = torch.where(can_TEKR, kgrid_TEKR.to(dtype),
                                  torch.full_like(kgrid_TEKR, big_iter, dtype=dtype)).amin(dim=-1)  # [T,E,K]
        else:
            # v41 fallback: dist(e@0, T@r) 不考虑派兵帧地图
            cross_iter = cache.cross_dist[1:Kmax_iter + 1][:, E_idx][:, :, target_idx.clamp(0, int(obs.P) - 1)].to(dtype)  # [Kk, E, T]
            reach_iter = spd_TEK.view(1, T, E, K_eta) * ks_iter.view(-1, 1, 1, 1)        # [Kk, T, E, K]
            can_iter = reach_iter >= cross_iter.permute(0, 2, 1).view(Kmax_iter, T, E, 1)
            big_iter = float(K_eta + 1)
            kgrid_iter = ks_iter.view(-1, 1, 1, 1).expand(-1, T, E, K_eta)
            arr_TEK = torch.where(can_iter, kgrid_iter, torch.full_like(kgrid_iter, big_iter)).amin(dim=0)  # [T, E, K]

        # 用 arr_TEK 重新算 arrived_by_k 和 e_send_time, 取 ships
        arrived_by_k = (arr_TEK <= kk) & not_self                                         # [T,E,K] 排除 e==T
        e_send_time2 = (kk - arr_TEK).clamp(min=0.0, max=float(H_axis - 1))               # [T,E,K]
        e_send_idx2 = e_send_time2.long()
        ships_TEK = ships_E.view(1, E, H_axis).expand(T, E, H_axis).gather(-1, e_send_idx2)
        owner_TEK = owner_E.view(1, E, H_axis).expand(T, E, H_axis).gather(-1, e_send_idx2)

        # owner check: e 在 e_send_time 仍是非我方阵营才能算敌方援军
        still_enemy = (owner_TEK != int(player_id)) & (owner_TEK >= 0)                   # [T,E,K]
        contrib = torch.where(arrived_by_k & still_enemy, ships_TEK, torch.zeros_like(ships_TEK))
    else:
        # legacy fallback: g_e + (k − arr_e)·prod_e
        e_prod = prod[E_idx].to(dtype)
        gar = e_ships_E.view(1, E, 1)
        prd = e_prod.view(1, E, 1)
        contrib = (gar + (kk - arr_e).clamp(min=0.0) * prd)
        contrib = torch.where(arrived_by_k, contrib, torch.zeros_like(contrib))

    sched = contrib.sum(dim=1)                                                          # [T,K] sum over enemy stars
    return sched


def friendly_reinforcement_schedule(obs, cache, target_idx, prod, player_id, *, K_eta, device, dtype,
                                    garrison_status, movement=None):
    """对偶版: 我方 muster 反扑 schedule — ``[T, K_eta]``.

    ``sched[T, j]`` = 我方占下 T 后, 在第 j 帧能从所有友星 F 收到的累积援军兵力.
    每颗友星 F 派兵到 T 最早 ``arr(F, T)`` 回合到, 要在 ``j`` 帧前到达 T 必须 ``F`` 在
    ``F_send_time = j − arr(F, T)`` 之前派出, 派出兵力 = ``garrison_status.ships[F,
    F_send_time]`` (do-nothing 投影, 自动含 F 收到的我方在途援军).

    用作 hold(x) 公式中的 garrison 加项 (post-eta 部分, 我落地后自我守军外的接力增援).
    """
    P = int(obs.P)
    pid = int(player_id)
    T = int(target_idx.numel())
    sched = torch.zeros(T, K_eta, device=device, dtype=dtype)
    if T == 0:
        return sched
    if movement is not None and os.environ.get("PRODUCER_EXACT_FRIENDLY_REINF") == "1":
        # As above, exact mode lets projected ownership at departure decide
        # whether a source is friendly, so include all currently live planets.
        F_idx = obs.alive.nonzero(as_tuple=False).reshape(-1)
        return _exact_reinforcement_schedule_from_future_departures(
            movement=movement,
            garrison_status=garrison_status,
            src_idx=F_idx,
            target_idx=target_idx,
            player_id=pid,
            K_eta=K_eta,
            device=device,
            dtype=dtype,
            owner_mode="friendly",
        )
    # 友方 arrival turns (复用 _side_arrival_turns)
    friendly_mask = obs.alive & (obs.owner_abs == pid)                                  # [P]
    arr_TF, f_ships_F, _d0 = _side_arrival_turns(obs, cache, target_idx, src_mask=friendly_mask,
                                                 K_eta=K_eta, device=device, dtype=dtype)  # [T,F],[F]
    F = int(f_ships_F.numel())
    if F == 0 or T == 0:
        return sched
    F_idx = friendly_mask.nonzero(as_tuple=False).reshape(-1)
    js = torch.arange(1, K_eta + 1, device=device, dtype=dtype)                         # [K] 我守 T 的回合
    arr_f = arr_TF.view(T, F, 1)                                                        # [T,F,1]
    jj = js.view(1, 1, K_eta)                                                           # [1,1,K]
    arrived_by_j = arr_f <= jj                                                          # [T,F,K]
    # [v41 fix] 排除 F == T (我占下后 T 自身不该再算成派援军给自己)
    not_self_F = (F_idx.view(1, F, 1) != target_idx.view(T, 1, 1))                      # [T,F,1]
    arrived_by_j = arrived_by_j & not_self_F                                            # [T,F,K]

    ships_p = garrison_status.ships                                                     # [P, H+1]
    owner_p = garrison_status.owner                                                     # [P, H+1]
    H_axis = int(ships_p.shape[-1])
    f_send_time = (jj - arr_f).clamp(min=0.0, max=float(H_axis - 1))                    # [T,F,K]
    f_send_idx = f_send_time.long()
    ships_F_all = ships_p[F_idx].to(dtype)                                              # [F, H+1]
    owner_F_all = owner_p[F_idx]                                                        # [F, H+1]
    ships_TFK = ships_F_all.view(1, F, H_axis).expand(T, F, H_axis).gather(-1, f_send_idx)
    owner_TFK = owner_F_all.view(1, F, H_axis).expand(T, F, H_axis).gather(-1, f_send_idx)

    # [v41] 不动点迭代 1 轮: 用 F 派出帧实际兵数算速度, 重算 arr.
    spd_TFK = fleet_speed(ships_TFK.clamp(min=1e-6)).to(dtype)                          # [T, F, K]
    # [v42] 派兵帧地图: dist(F@F_send_time, T@(F_send_time+r)) 取代 dist(F@0, T@r).
    Kmax_iter = min(int(K_eta), int(movement.x.shape[0]) - 1) if movement is not None else min(int(K_eta), cache.cross_dist.shape[0] - 1)
    ks_iter = torch.arange(1, Kmax_iter + 1, device=device, dtype=dtype)                # [Kk]
    if movement is not None:
        d_TFKR = _dist_send_fly_4d(movement, src_idx=F_idx, tgt_idx=target_idx,
                                    e_send_idx=f_send_idx, K_eta=Kmax_iter,
                                    device=device, dtype=dtype)                          # [T,F,K,R]
        reach_TFKR = spd_TFK.view(T, F, K_eta, 1) * ks_iter.view(1, 1, 1, Kmax_iter)
        can_TFKR = reach_TFKR >= d_TFKR
        big_iter = float(K_eta + 1)
        kgrid_TFKR = ks_iter.view(1, 1, 1, Kmax_iter).expand(T, F, K_eta, Kmax_iter)
        arr_TFK = torch.where(can_TFKR, kgrid_TFKR.to(dtype),
                              torch.full_like(kgrid_TFKR, big_iter, dtype=dtype)).amin(dim=-1)  # [T,F,K]
    else:
        cross_iter = cache.cross_dist[1:Kmax_iter + 1][:, F_idx][:, :, target_idx.clamp(0, int(obs.P) - 1)].to(dtype)  # [Kk, F, T]
        reach_iter = spd_TFK.view(1, T, F, K_eta) * ks_iter.view(-1, 1, 1, 1)           # [Kk, T, F, K]
        can_iter = reach_iter >= cross_iter.permute(0, 2, 1).view(Kmax_iter, T, F, 1)
        big_iter = float(K_eta + 1)
        kgrid_iter = ks_iter.view(-1, 1, 1, 1).expand(-1, T, F, K_eta)
        arr_TFK = torch.where(can_iter, kgrid_iter, torch.full_like(kgrid_iter, big_iter)).amin(dim=0)  # [T, F, K]

    arrived_by_j = (arr_TFK <= jj) & not_self_F                                            # [T,F,K] 排除 F==T
    f_send_time2 = (jj - arr_TFK).clamp(min=0.0, max=float(H_axis - 1))
    f_send_idx2 = f_send_time2.long()
    ships_TFK = ships_F_all.view(1, F, H_axis).expand(T, F, H_axis).gather(-1, f_send_idx2)
    owner_TFK = owner_F_all.view(1, F, H_axis).expand(T, F, H_axis).gather(-1, f_send_idx2)

    still_mine = (owner_TFK == pid)                                                      # F 在派出帧仍是我的
    contrib = torch.where(arrived_by_j & still_mine, ships_TFK, torch.zeros_like(ships_TFK))
    sched = contrib.sum(dim=1)                                                          # [T,K]
    # The public contract is cumulative-by-deadline: support that can arrive by
    # frame k is also available by every later frame.  The one-step fallback
    # above recomputes a fresh departure frame for each deadline, which can make
    # a source disappear on later deadlines even though it could have used the
    # earlier feasible departure.  Restore the cumulative invariant cheaply.
    if not os.environ.get("PRODUCER_NO_FRIENDLY_SCHED_CUMMAX"):
        sched = sched.cummax(dim=-1).values
    return sched


def build_attack_candidates(
    *,
    movement: PlanetMovement,
    cache,
    obs,
    player_id: int,
    source_idx: Tensor, source_exists: Tensor,
    target_idx: Tensor, target_exists: Tensor,
    target_is_mine: Tensor, target_prod: Tensor,
    drain: Tensor, source_ships: Tensor, src_prod: Tensor,
    floor: Tensor, K: int, K_eta: int, eta_cap: Tensor,
    delay_max: int, P: int, S: int, T: int, device, dtype,
    enemy_arrivals_TK: Tensor | None = None,
    friendly_arrivals_TK: Tensor | None = None,
    target_pre_mine_ships_TK: Tensor | None = None,
    target_pre_owner_TK: Tensor | None = None,
    target_pre_ships_TK: Tensor | None = None,
    same_step_arrivals_TKA: Tensor | None = None,
    capture_reinforcement_TK: Tensor | None = None,
    capture_overhead: float = 1.0,
    source_launch_ok_SD: Tensor | None = None,
    source_launch_ships_SD: Tensor | None = None,
) -> AttackCandidates:
    """Generate the objective attack-candidate table (framework mechanism).

    For each ``(source, target)`` pair, generates delayed-launch variants d∈{0..delay_max}
    — fleet size ``drain + d·prod`` (capped), aimed with ``intercept_angle(launch_turn=d)``
    so source/target/obstacle positions are taken d steps ahead, total arrival turn
    ``d + flight``. Validity = geometric viability ∧ within reach cap ∧ clears the
    capture floor at the arrival turn ∧ source≠target ∧ source/target exist. The floor
    test uses MULTI-SOURCE ADMISSION: the effective fleet is this source's size PLUS the
    drain of every friendly source nearer to the target (they can co-strike), so high-
    garrison stars enter the pool. The table keeps single-source rows and also adds
    multi-source convergence rows for target/delay pairs that only clear the floor
    together. Pure mechanism; no strategy (the opportunity-cost discount + bonuses
    are applied by the caller).
    """
    D = delay_max + 1
    delays = torch.arange(D, dtype=dtype, device=device)                          # [D]
    if source_launch_ok_SD is None:
        source_launch_ok_SD = source_exists.view(S, 1).expand(S, D)
    else:
        source_launch_ok_SD = source_launch_ok_SD.to(device=device, dtype=torch.bool)
        if tuple(source_launch_ok_SD.shape) != (S, D):
            raise ValueError(
                f"source_launch_ok_SD must have shape {(S, D)}, got "
                f"{tuple(source_launch_ok_SD.shape)}"
            )
    src_cap_d = (source_ships.view(S, 1) + delays.view(1, D) * src_prod.view(S, 1)).floor()  # [S, D]
    if source_launch_ships_SD is not None:
        source_launch_ships_SD = source_launch_ships_SD.to(device=device, dtype=dtype)
        if tuple(source_launch_ships_SD.shape) != (S, D):
            raise ValueError(
                f"source_launch_ships_SD must have shape {(S, D)}, got "
                f"{tuple(source_launch_ships_SD.shape)}"
            )
        # Delayed launches spend the ships actually present at the future action
        # frame.  ``drain`` may already have been limited by a known in-flight hit,
        # so adding ``delay * prod`` again can otherwise overstate affordability.
        src_cap_d = torch.minimum(src_cap_d, source_launch_ships_SD.floor().clamp(min=0.0))
    drain_d = (drain.view(S, 1) + delays.view(1, D) * src_prod.view(S, 1)).floor()  # [S, D]
    drain_d = torch.minimum(drain_d, src_cap_d)                                   # [S, D]
    sizes_d = drain_d.view(S, 1, D).expand(S, T, D)                               # [S, T, D]

    src_ST = source_idx.view(S, 1).expand(S, T)                                  # [S,T]
    tgt_ST = target_idx.view(1, T).expand(S, T)                                  # [S,T]
    angle_cols, flighteta_cols, viable_cols = [], [], []
    for _d in range(D):
        _sizes_col = sizes_d[..., _d]                                            # [S,T] fleet size at delay d
        _aim = intercept_angle(movement, src_ST, tgt_ST, _sizes_col, launch_turn=_d)
        angle_cols.append(_aim["angle"])
        flighteta_cols.append(_aim["eta"])
        viable_cols.append(_aim["viable"])
    angle_d_full = torch.stack(angle_cols, dim=-1)                               # [S,T,D]
    flight_eta_d = torch.stack(flighteta_cols, dim=-1)                           # [S,T,D]
    viable_geom = torch.stack(viable_cols, dim=-1)                               # [S,T,D]
    eta_d = flight_eta_d + delays.view(1, 1, D)                                  # [S,T,D] hold + travel
    viable_d = viable_geom & (eta_d <= eta_cap.view(1, T, 1))                    # [S,T,D]

    # Capture-floor at delayed arrival turn.
    if K > 0:
        k_arr_d = (eta_d.clamp(min=1.0, max=float(K)).ceil().long() - 1).clamp(0, K - 1)  # [S,T,D]
        floor_at_arr_d = floor.view(1, T, 1, K).expand(S, T, D, K).gather(
            -1, k_arr_d.unsqueeze(-1)).squeeze(-1)                                # [S, T, D]
    else:
        floor_at_arr_d = torch.ones(S, T, D, dtype=dtype, device=device)

    src_neq_tgt = (source_idx.view(S, 1) != target_idx.view(1, T)).unsqueeze(-1)  # [S,T,1]
    # Multi-source convergence admission: effective fleet = own size + drain of every
    # friendly source that can reach the same target (geometry-viable, bidirectional).
    # [v48 fix] 必须用 source_exists mask 掉 padding 源.
    # [v52] 双向 admission: 对每个 (target, delay), 统计该 delay 下所有几何可达源的
    # 实际 send — 如果集体够 floor 就全部 admit.
    # 迭代贪心负责协调谁先谁后 (wave1 最近源削弱, wave2 次源补刀).
    _src_can_reach_td = (
        viable_d
        & source_launch_ok_SD.view(S, 1, D)
        & source_exists.view(S, 1, 1)
        & target_exists.view(1, T, 1)
        & src_neq_tgt
    )                                                                            # [S, T, D]
    _reachable_send_d = sizes_d * _src_can_reach_td.to(dtype)                   # [S, T, D]
    _total_reachable_per_td = _reachable_send_d.sum(dim=0)                      # [T, D]
    _others_send_d = _total_reachable_per_td.view(1, T, D) - _reachable_send_d  # [S, T, D]
    eff_fleet_d = sizes_d + _others_send_d                                      # [S, T, D]
    clears_floor_d = eff_fleet_d >= floor_at_arr_d                              # [S, T, D]

    valid_d = (
        viable_d & clears_floor_d & (sizes_d >= 1.0) & src_neq_tgt
        & source_launch_ok_SD.view(S, 1, D)
        & source_exists.view(S, 1, 1) & target_exists.view(1, T, 1)
    )                                                                            # [S, T, D]

    # [v26] Deterministic hold(x): turns we keep target T after capturing with this fleet.
    # THREAT SOURCE = precise ballistic arrival schedule of every IN-FLIGHT enemy fleet,
    # from the engine-exact forward sim (fleet_buckets via arrivals_by_owner). NO proxy:
    # enemy_arrivals_TK[t, j] = enemy ships that actually hit target t on absolute future
    # turn j (1..K_eta). Two-phase (用户 spec):
    #   • arrivals at turn ≤ our eta  → defenders we must punch through → already in
    #     capture_floor → EXCLUDE from the hold race (they don't re-attack post-capture).
    #   • arrivals at turn > our eta  → race our growing garrison (r0 + prod·turns);
    #     hold = (first turn cumulative post-eta arrivals exceed garrison) − eta.
    abs_turns = torch.arange(1, K_eta + 1, device=device, dtype=dtype)             # [Kw] absolute turns
    prodT_T = target_prod.to(dtype)                                                # [T]
    r0_capture = sizes_d - floor_at_arr_d
    immediate_lost_d = torch.zeros(S, T, D, dtype=torch.bool, device=device)
    if K > 0 and target_pre_owner_TK is not None and target_pre_ships_TK is not None:
        pre_owner_TK = target_pre_owner_TK[..., :K].to(device=device, dtype=torch.long)
        pre_ships_TK = target_pre_ships_TK[..., :K].to(dtype=dtype, device=device)
        pre_owner_at_arr = pre_owner_TK.view(1, T, 1, K).expand(S, T, D, K).gather(
            -1, k_arr_d.unsqueeze(-1)).squeeze(-1)                                  # [S,T,D]
        pre_ships_at_arr = pre_ships_TK.view(1, T, 1, K).expand(S, T, D, K).gather(
            -1, k_arr_d.unsqueeze(-1)).squeeze(-1)                                  # [S,T,D]
        if same_step_arrivals_TKA is not None:
            arr_TKA = same_step_arrivals_TKA[:, :K, :].to(dtype=dtype, device=device)
            A_arr = int(arr_TKA.shape[-1])
            arr_at = arr_TKA.view(1, T, 1, K, A_arr).expand(S, T, D, K, A_arr).gather(
                -2, k_arr_d.unsqueeze(-1).unsqueeze(-1).expand(S, T, D, 1, A_arr)
            ).squeeze(-2)                                                           # [S,T,D,A]
            if int(player_id) < A_arr:
                fleet_by_owner = arr_at.clone()
                fleet_by_owner[..., int(player_id)] = fleet_by_owner[..., int(player_id)] + sizes_d
                top2 = fleet_by_owner.topk(k=min(2, A_arr), dim=-1)
                top_ships = top2.values[..., 0]
                second_ships = (
                    top2.values[..., 1]
                    if A_arr >= 2
                    else torch.zeros_like(top_ships)
                )
                survivor_owner = top2.indices[..., 0].to(torch.long)
                fleet_tied = top_ships == second_ships
                survivor_ships = torch.where(
                    fleet_tied,
                    torch.zeros_like(top_ships),
                    (top_ships - second_ships).clamp(min=0.0),
                )
            else:
                survivor_owner = torch.full_like(pre_owner_at_arr, -1)
                survivor_ships = torch.zeros_like(pre_ships_at_arr)
        else:
            survivor_owner = torch.full_like(pre_owner_at_arr, int(player_id))
            survivor_ships = sizes_d
        if capture_reinforcement_TK is not None:
            reinf_TK = capture_reinforcement_TK[..., :K].to(dtype=dtype, device=device)
            reinf_at_arr = reinf_TK.view(1, T, 1, K).expand(S, T, D, K).gather(
                -1, k_arr_d.unsqueeze(-1)).squeeze(-1)
        else:
            reinf_at_arr = torch.zeros_like(sizes_d)
        has_survivor = survivor_ships > 0.0
        same_owner = pre_owner_at_arr == survivor_owner
        diff = pre_ships_at_arr - survivor_ships
        attacker_wins = (~same_owner) & (diff < 0.0)
        same_player = same_owner & (pre_owner_at_arr == int(player_id))
        player_attacker_wins = attacker_wins & (survivor_owner == int(player_id))
        player_defends = (~attacker_wins) & (pre_owner_at_arr == int(player_id))
        player_after = torch.where(
            same_player,
            pre_ships_at_arr + survivor_ships,
            torch.where(
                player_attacker_wins,
                (survivor_ships - pre_ships_at_arr).clamp(min=0.0),
                torch.where(
                    player_defends & has_survivor,
                    (pre_ships_at_arr - survivor_ships).clamp(min=0.0),
                    torch.where(
                        player_defends,
                        pre_ships_at_arr,
                        torch.zeros_like(pre_ships_at_arr),
                    ),
                ),
            ),
        )
        capture_cell = pre_owner_at_arr != int(player_id)
        immediate_lost_d = (~capture_cell) & (reinf_at_arr > player_after)
        r0_d = torch.where(
            capture_cell,
            (player_after - float(capture_overhead) - reinf_at_arr).clamp(min=0.0),
            (player_after - reinf_at_arr).clamp(min=0.0),
        )
    elif K > 0 and target_pre_mine_ships_TK is not None:
        pre_mine_TK = target_pre_mine_ships_TK[..., :K].to(dtype=dtype, device=device)
        pre_mine_at_arr = pre_mine_TK.view(1, T, 1, K).expand(S, T, D, K).gather(
            -1, k_arr_d.unsqueeze(-1)).squeeze(-1)                                  # [S,T,D], -1 if not mine at arrival
        if same_step_arrivals_TKA is not None:
            arr_TKA = same_step_arrivals_TKA[:, :K, :].to(dtype=dtype, device=device)
            A_arr = int(arr_TKA.shape[-1])
            arr_at = arr_TKA.view(1, T, 1, K, A_arr).expand(S, T, D, K, A_arr).gather(
                -2, k_arr_d.unsqueeze(-1).unsqueeze(-1).expand(S, T, D, 1, A_arr)
            ).squeeze(-2)                                                           # [S,T,D,A]
            if int(player_id) < A_arr:
                fleet_by_owner = arr_at.clone()
                fleet_by_owner[..., int(player_id)] = fleet_by_owner[..., int(player_id)] + sizes_d
                top2 = fleet_by_owner.topk(k=min(2, A_arr), dim=-1)
                top_ships = top2.values[..., 0]
                second_ships = (
                    top2.values[..., 1]
                    if A_arr >= 2
                    else torch.zeros_like(top_ships)
                )
                top_owner = top2.indices[..., 0].to(torch.long)
                fleet_tied = top_ships == second_ships
                survivor_ships = torch.where(
                    fleet_tied,
                    torch.zeros_like(top_ships),
                    (top_ships - second_ships).clamp(min=0.0),
                )
                same_owner = top_owner == int(player_id)
                diff = pre_mine_at_arr - survivor_ships
                attacker_wins = (~same_owner) & (diff < 0.0)
                combat_ships = torch.where(same_owner, pre_mine_at_arr + survivor_ships, diff.abs())
                r0_reinforce = torch.where(
                    attacker_wins,
                    torch.zeros_like(combat_ships),
                    combat_ships,
                )
            else:
                r0_reinforce = pre_mine_at_arr.clamp(min=0.0) + sizes_d
        else:
            r0_reinforce = pre_mine_at_arr.clamp(min=0.0) + sizes_d
        r0_d = torch.where(pre_mine_at_arr >= 0.0, r0_reinforce, r0_capture).clamp(min=0.0)
    else:
        r0_d = r0_capture.clamp(min=0.0)                                             # [S,T,D] surviving garrison after capture
    eta_e = eta_d.unsqueeze(-1)                                                     # [S,T,D,1]
    eta_turn_e = eta_d.ceil().unsqueeze(-1)                                         # [S,T,D,1] integer engine arrival turn
    jgrid = abs_turns.view(1, 1, 1, K_eta)                                         # absolute turn axis
    # [v44] garrison(j) = r0 + prod · max(0, j - eta): 自产从我落地 (eta) 才开始累积.
    # 之前 garrison = r0 + prod·j 多算了 eta 帧的自产 (我落地前我还没占, 不该入账).
    elapsed = (jgrid - eta_turn_e).clamp(min=0.0)                                  # [S,T,D,Kw]
    garrison = r0_d.unsqueeze(-1) + prodT_T.view(1, T, 1, 1) * elapsed             # [S,T,D,Kw]
    # [v40] 友方 post-eta 在途到 T → 加进 garrison 帮我守 (用户: 收益公式要算友方在途)。
    if friendly_arrivals_TK is not None:
        f_arr_j = friendly_arrivals_TK[:, :K_eta].to(dtype).view(1, T, 1, K_eta)   # [1,T,1,Kw]
        post_eta_f = (jgrid > eta_turn_e)                                           # [S,T,D,Kw]
        f_contrib = torch.where(post_eta_f, f_arr_j, torch.zeros_like(f_arr_j))    # 仅 post-eta
        f_cum = torch.cumsum(f_contrib, dim=-1)                                    # [S,T,D,Kw]
        # The target-level friendly schedule is computed before this candidate's
        # source debit.  Without this correction, the same source ships can be
        # counted once as the attacking fleet and again as future support to the
        # captured target.  Keep support from other friendly planets, but remove
        # the ships this candidate already committed from the post-eta cumulative
        # friendly credit.
        f_cum = (f_cum - sizes_d.unsqueeze(-1)).clamp(min=0.0)
        garrison = garrison + f_cum
    if enemy_arrivals_TK is not None:
        arr_j = enemy_arrivals_TK[:, :K_eta].to(dtype).view(1, T, 1, K_eta)        # [1,T,1,Kw] precise ballistic
        post_eta = (jgrid > eta_turn_e)                                            # [S,T,D,Kw] arrives after our integer landing turn
        contrib = torch.where(post_eta, arr_j, torch.zeros_like(arr_j))            # only post-eta arrivals race us
        cum = torch.cumsum(contrib, dim=-1)                                        # [S,T,D,Kw]
        breached = cum > garrison                                                  # [S,T,D,Kw]
        bj = torch.where(breached, jgrid.expand_as(breached),
                         torch.full_like(garrison, float(K_eta + 1)))
        first_breach = bj.amin(dim=-1)                                             # [S,T,D] absolute breach turn
        hold_d = (first_breach - eta_d.ceil()).clamp(min=0.0, max=float(K_eta))    # [S,T,D]
    else:
        # No in-flight schedule available → keep target to horizon (neutral).
        hold_d = torch.full((S, T, D), float(K_eta), device=device, dtype=dtype)
    hold_d = torch.where(immediate_lost_d, torch.zeros_like(hold_d), hold_d)

    # Pack one candidate per (source, target, delay), plus one real multi-source
    # candidate per (target, delay).  The older single-source rows are kept so
    # profitable solo captures behave identically; multi rows make the admission
    # gate's "all reachable sources can co-strike" premise visible to exact
    # scoring and greedy selection.
    L = S
    C_single = S * T * D
    src_single = source_idx.view(S, 1, 1).expand(S, T, D).reshape(C_single, 1)
    tgt_single = target_idx.view(1, T, 1).expand(S, T, D).reshape(C_single)
    tsh_single = torch.arange(T, device=device).view(1, T, 1).expand(S, T, D).reshape(C_single)
    delay_single = delays.view(1, 1, D).expand(S, T, D).reshape(C_single).to(torch.long)
    src_prod_single = src_prod.view(S, 1, 1).expand(S, T, D).reshape(C_single, 1)
    send_single = torch.where(valid_d, sizes_d, torch.zeros_like(sizes_d)).reshape(C_single, 1)
    angle_single = angle_d_full.reshape(C_single, 1)
    eta_single = torch.where(valid_d, eta_d, torch.ones_like(eta_d)).reshape(C_single, 1)
    active_single = valid_d.reshape(C_single, 1)
    valid_single = valid_d.reshape(C_single)
    hold_single = hold_d.reshape(C_single)
    cost_single = torch.maximum(sizes_d, floor_at_arr_d).reshape(C_single)

    pad_src = source_idx[:1].view(1, 1).expand(C_single, L)
    cand_src_single = pad_src.clone()
    cand_src_single[:, :1] = src_single
    cand_send_single = torch.zeros(C_single, L, dtype=dtype, device=device)
    cand_send_single[:, :1] = send_single
    cand_angle_single = torch.zeros(C_single, L, dtype=dtype, device=device)
    cand_angle_single[:, :1] = angle_single
    cand_eta_single = torch.ones(C_single, L, dtype=dtype, device=device)
    cand_eta_single[:, :1] = eta_single
    cand_active_single = torch.zeros(C_single, L, dtype=torch.bool, device=device)
    cand_active_single[:, :1] = active_single

    C_multi = T * D
    tgt_multi = target_idx.view(T, 1).expand(T, D).reshape(C_multi)
    tsh_multi = torch.arange(T, device=device).view(T, 1).expand(T, D).reshape(C_multi)
    delay_multi = delays.view(1, D).expand(T, D).reshape(C_multi).to(torch.long)
    src_prod_multi = src_prod.view(1, S, 1).expand(T, S, D).permute(0, 2, 1).reshape(C_multi, L)
    cand_src_multi = source_idx.view(1, S, 1).expand(T, S, D).permute(0, 2, 1).reshape(C_multi, L)
    multi_active_TSD = _src_can_reach_td.permute(1, 0, 2)                       # [T, S, D]
    send_multi_TSD = sizes_d.permute(1, 0, 2)                                    # [T,S,D]
    cand_send_raw_multi = send_multi_TSD.permute(0, 2, 1).reshape(C_multi, L)
    cand_active_multi = (
        multi_active_TSD.permute(0, 2, 1).reshape(C_multi, L)
        & (cand_send_raw_multi >= 1.0)
    )
    cand_send_multi = torch.where(
        cand_active_multi,
        cand_send_raw_multi,
        torch.zeros(C_multi, L, dtype=dtype, device=device),
    )
    cand_angle_multi = torch.where(
        cand_active_multi,
        angle_d_full.permute(1, 2, 0).reshape(C_multi, L),
        torch.zeros(C_multi, L, dtype=dtype, device=device),
    )
    cand_eta_multi = torch.where(
        cand_active_multi,
        eta_d.permute(1, 2, 0).reshape(C_multi, L),
        torch.ones(C_multi, L, dtype=dtype, device=device),
    )
    multi_send_sum = cand_send_multi.sum(dim=-1)                                  # [C_multi]
    floor_multi_src = floor_at_arr_d.permute(1, 2, 0).reshape(C_multi, L)
    floor_multi = torch.where(
        cand_active_multi,
        floor_multi_src,
        torch.zeros_like(floor_multi_src),
    ).amax(dim=-1)
    multi_any = cand_active_multi.any(dim=-1)
    multi_count = cand_active_multi.to(torch.long).sum(dim=-1)
    multi_valid = multi_any & (multi_count >= 2) & (multi_send_sum >= floor_multi)
    hold_multi_src = hold_d.permute(1, 2, 0).reshape(C_multi, L)
    hold_multi_TD = torch.where(
        cand_active_multi,
        hold_multi_src,
        torch.zeros_like(hold_multi_src),
    ).amax(dim=-1)
    # For staggered multi-source rows, the occupation cannot be valued from an
    # early contributor's personal hold window.  Production accounting below uses
    # the row's latest active arrival as the capture/arrival time, so the hold
    # horizon must also come from that latest arrival bucket.  Same-bucket rows are
    # handled by the combined-survivor exact block immediately below.
    eta_bucket_multi = cand_eta_multi.clamp(min=1.0, max=float(max(K, 1))).ceil().long()
    active_bucket = torch.where(
        cand_active_multi,
        eta_bucket_multi,
        torch.zeros_like(eta_bucket_multi),
    )
    max_bucket = active_bucket.amax(dim=-1)
    latest_bucket_active = cand_active_multi & (eta_bucket_multi == max_bucket.view(C_multi, 1))
    hold_multi_latest = torch.where(
        latest_bucket_active,
        hold_multi_src,
        torch.zeros_like(hold_multi_src),
    ).amax(dim=-1)
    min_bucket = torch.where(
        cand_active_multi,
        eta_bucket_multi,
        torch.full_like(eta_bucket_multi, max(K, 1) + 1),
    ).amin(dim=-1)
    same_arrival_bucket = multi_any & (max_bucket == min_bucket)
    staggered_arrival_bucket = multi_any & ~same_arrival_bucket
    hold_multi_TD = torch.where(
        staggered_arrival_bucket,
        hold_multi_latest,
        hold_multi_TD,
    )
    # Same-arrival multi-source rows represent a single combined fleet bucket in
    # the engine.  Their hold horizon must be computed from the combined
    # survivor, not from the best single contributor's survivor.
    if bool(same_arrival_bucket.any()):
        eta_multi = torch.where(
            cand_active_multi,
            cand_eta_multi,
            torch.zeros_like(cand_eta_multi),
        ).amax(dim=-1).clamp(min=1.0)                                             # [C_multi]
        r0_multi = (multi_send_sum - floor_multi).clamp(min=0.0)                  # [C_multi]
        if K > 0 and target_pre_owner_TK is not None and target_pre_ships_TK is not None:
            k_multi = (eta_multi.clamp(min=1.0, max=float(K)).ceil().long() - 1).clamp(0, K - 1)
            pre_owner_m = target_pre_owner_TK.to(device=device, dtype=torch.long)[tsh_multi, k_multi]
            pre_ships_m = target_pre_ships_TK.to(dtype=dtype, device=device)[tsh_multi, k_multi]
            if same_step_arrivals_TKA is not None:
                arr_m = same_step_arrivals_TKA[:, :K, :].to(dtype=dtype, device=device)[tsh_multi, k_multi, :]
                A_arr = int(arr_m.shape[-1])
                if int(player_id) < A_arr:
                    fleet_by_owner = arr_m.clone()
                    fleet_by_owner[:, int(player_id)] = fleet_by_owner[:, int(player_id)] + multi_send_sum
                    top2 = fleet_by_owner.topk(k=min(2, A_arr), dim=-1)
                    top_ships = top2.values[:, 0]
                    second_ships = (
                        top2.values[:, 1]
                        if A_arr >= 2
                        else torch.zeros_like(top_ships)
                    )
                    survivor_owner = top2.indices[:, 0].to(torch.long)
                    tied = top_ships == second_ships
                    survivor_ships = torch.where(
                        tied,
                        torch.zeros_like(top_ships),
                        (top_ships - second_ships).clamp(min=0.0),
                    )
                else:
                    survivor_owner = torch.full_like(pre_owner_m, -1)
                    survivor_ships = torch.zeros_like(pre_ships_m)
            else:
                survivor_owner = torch.full_like(pre_owner_m, int(player_id))
                survivor_ships = multi_send_sum
            if capture_reinforcement_TK is not None:
                reinf_m = capture_reinforcement_TK[:, :K].to(dtype=dtype, device=device)[tsh_multi, k_multi]
            else:
                reinf_m = torch.zeros_like(multi_send_sum)
            has_survivor = survivor_ships > 0.0
            same_owner = pre_owner_m == survivor_owner
            diff = pre_ships_m - survivor_ships
            attacker_wins = (~same_owner) & (diff < 0.0)
            same_player = same_owner & (pre_owner_m == int(player_id))
            player_attacker_wins = attacker_wins & (survivor_owner == int(player_id))
            player_defends = (~attacker_wins) & (pre_owner_m == int(player_id))
            player_after = torch.where(
                same_player,
                pre_ships_m + survivor_ships,
                torch.where(
                    player_attacker_wins,
                    (survivor_ships - pre_ships_m).clamp(min=0.0),
                    torch.where(
                        player_defends & has_survivor,
                        (pre_ships_m - survivor_ships).clamp(min=0.0),
                        torch.where(player_defends, pre_ships_m, torch.zeros_like(pre_ships_m)),
                    ),
                ),
            )
            capture_cell = pre_owner_m != int(player_id)
            r0_multi = torch.where(
                capture_cell,
                (player_after - float(capture_overhead) - reinf_m).clamp(min=0.0),
                (player_after - reinf_m).clamp(min=0.0),
            )
        if enemy_arrivals_TK is not None:
            jgrid_m = abs_turns.view(1, K_eta)
            eta_m = eta_multi.view(C_multi, 1)
            eta_turn_m = eta_multi.ceil().view(C_multi, 1)
            elapsed_m = (jgrid_m - eta_turn_m).clamp(min=0.0)
            garrison_m = (
                r0_multi.view(C_multi, 1)
                + prodT_T[tsh_multi].to(dtype).view(C_multi, 1) * elapsed_m
            )
            post_eta_m = jgrid_m > eta_turn_m
            if friendly_arrivals_TK is not None:
                f_arr_m = friendly_arrivals_TK[:, :K_eta].to(dtype=dtype, device=device)[tsh_multi]
                f_cum_m = torch.cumsum(
                    torch.where(post_eta_m, f_arr_m, torch.zeros_like(f_arr_m)),
                    dim=-1,
                )
                f_cum_m = (f_cum_m - multi_send_sum.view(C_multi, 1)).clamp(min=0.0)
                garrison_m = garrison_m + f_cum_m
            e_arr_m = enemy_arrivals_TK[:, :K_eta].to(dtype=dtype, device=device)[tsh_multi]
            cum_m = torch.cumsum(
                torch.where(post_eta_m, e_arr_m, torch.zeros_like(e_arr_m)),
                dim=-1,
            )
            breached_m = cum_m > garrison_m
            bj_m = torch.where(
                breached_m,
                jgrid_m.expand_as(breached_m),
                torch.full_like(garrison_m, float(K_eta + 1)),
            )
            hold_multi_combined = (bj_m.amin(dim=-1) - eta_multi.ceil()).clamp(min=0.0, max=float(K_eta))
        else:
            hold_multi_combined = torch.full((C_multi,), float(K_eta), dtype=dtype, device=device)
        hold_multi_TD = torch.where(
            same_arrival_bucket,
            hold_multi_combined,
            hold_multi_TD,
        )
    cost_multi = torch.maximum(multi_send_sum, floor_multi)

    cand_src = torch.cat([cand_src_single, cand_src_multi], dim=0)
    cand_send = torch.cat([cand_send_single, cand_send_multi], dim=0)
    cand_angle = torch.cat([cand_angle_single, cand_angle_multi], dim=0)
    cand_eta = torch.cat([cand_eta_single, cand_eta_multi], dim=0)
    cand_active = torch.cat([cand_active_single, cand_active_multi], dim=0)
    cand_valid = torch.cat([valid_single, multi_valid], dim=0)
    cand_tgt_slot = torch.cat([tgt_single, tgt_multi], dim=0)
    cand_tgt_short = torch.cat([tsh_single, tsh_multi], dim=0)
    cand_delay = torch.cat([delay_single, delay_multi], dim=0)
    pad_prod = torch.zeros(C_single, L, dtype=dtype, device=device)
    pad_prod[:, :1] = src_prod_single
    cand_src_prod = torch.cat([pad_prod, src_prod_multi], dim=0)
    cand_hold = torch.cat([hold_single, hold_multi_TD], dim=0)
    cand_cost = torch.cat([cost_single, cost_multi], dim=0)
    keep_valid = cand_valid
    if bool(keep_valid.any()) and bool((~keep_valid).any()):
        cand_src = cand_src[keep_valid]
        cand_send = cand_send[keep_valid]
        cand_angle = cand_angle[keep_valid]
        cand_eta = cand_eta[keep_valid]
        cand_active = cand_active[keep_valid]
        cand_valid = cand_valid[keep_valid]
        cand_tgt_slot = cand_tgt_slot[keep_valid]
        cand_tgt_short = cand_tgt_short[keep_valid]
        cand_delay = cand_delay[keep_valid]
        cand_src_prod = cand_src_prod[keep_valid]
        cand_hold = cand_hold[keep_valid]
        cand_cost = cand_cost[keep_valid]
    C = int(cand_valid.shape[0])
    cand_is_def = target_is_mine[cand_tgt_short]                                 # [C]
    return AttackCandidates(
        cand_src=cand_src, cand_send=cand_send, cand_angle=cand_angle, cand_eta=cand_eta,
        cand_active=cand_active, cand_valid=cand_valid, cand_tgt_slot=cand_tgt_slot,
        cand_tgt_short=cand_tgt_short, cand_is_def=cand_is_def, cand_delay=cand_delay,
        cand_src_prod=cand_src_prod, cand_hold=cand_hold, cand_cost=cand_cost, C=C, L=L, D=D,
    )


def largest_initial_player_count(obs_tensors: dict) -> int:
    """Player count for the match, preferring initial owners over live metadata."""
    initial = obs_tensors["initial_planets"]      # [P, 7]
    pid = initial[:, 0]
    owner = initial[:, 1]
    mask = (pid >= 0) & (owner >= 0)
    owners = owner[mask]
    n_max = 2
    if owners.numel() > 0:
        n_max = max(n_max, int(torch.unique(owners.long()).numel()))
        if n_max in (2, 4):
            return n_max
    metadata_count = obs_tensors.get("player_count")
    if metadata_count is not None:
        count = (
            int(metadata_count.flatten()[0].item())
            if isinstance(metadata_count, Tensor)
            else int(metadata_count)
        )
        if count in (2, 4):
            return count
    return n_max


# ---------------------------------------------------------------------------
# Scoring (P2): candidate launches -> competitive net-ship-delta
# ---------------------------------------------------------------------------


def make_launch_set(
    *,
    source_slots: Tensor,   # [C, L] long
    target_slots: Tensor,   # [C, L] long
    ships: Tensor,          # [C, L] float
    eta: Tensor,            # [C, L] float (steps to arrival, >= 1)
    valid: Tensor,          # [C, L] bool
    player_id: int,
    depart_turn: Tensor | None = None,  # [C, L] long: turns until the fleet departs
) -> LaunchSet:
    """Build a candidate-axis ``LaunchSet`` owned by ``player_id``."""
    owner = torch.full_like(source_slots, int(player_id), dtype=torch.long)
    return LaunchSet(
        source_slots=source_slots.to(torch.long),
        target_slots=target_slots.to(torch.long),
        ships=ships,
        eta=eta,
        owner=owner,
        valid=valid.to(torch.bool),
        depart_turn=None if depart_turn is None else depart_turn.to(torch.long),
    )


def competitive_score(
    diff: GarrisonFlowDiff,
    *,
    player_id: int,
    combat_mode: Tensor | str = "full",
    prod_mode: Tensor | None = None,
    prod_hold_frac: Tensor | None = None,
    combat_scale: Tensor | None = None,
) -> Tensor:
    """Competitive score per candidate. ``[*prefix]``.

    Decomposed into a PRODUCTION term and a COMBAT term so combat can be handled
    differently per candidate (ship losses mean different things by context):

      production = Δproduced_me − Σ_opp Δproduced_opp   (occupation value; capturing
                   an enemy planet is "double" — I gain prod and they lose it)
      combat     = depends on ``combat_mode``:
        - "full"    (4P):    full Δnet (= produced − combat) competitive diff. Ship
                             losses are NOT symmetric — a third party profits when I
                             trade with one opponent — so keep the combat term.
        - "none"    (2P vs enemy): IGNORE combat entirely. My losses and the
                             enemy's losses are symmetric existing-ship trades that
                             cancel; only the occupation (production) outcome matters.
        - "self"    (vs neutral): subtract only MY combat losses. Ships spent vs a
                             neutral garrison are a real net loss (the neutral isn't
                             an opponent whose loss helps me), with no offsetting
                             enemy loss to cancel them.

    ``combat_mode`` may be a per-candidate string-coded tensor (0=full,1=none,2=self)
    or a single string applied to all.
    """
    A = int(diff.net_ship_delta.shape[-1])
    pid = int(player_id)
    prod_d = diff.ships_produced_delta              # [*prefix, A]
    comb_d = diff.ships_lost_combat_delta           # [*prefix, A]

    # Production competitive diff: full = Δprod_me − Σ_opp Δprod_opp (double: I gain,
    # they lose). prod_mode (per-candidate, 0=full / 1=self_prod) can drop the
    # opponent-loss half — in 4P/3P, capturing an enemy star mainly helps bystanders,
    # so only my own production gain counts competitively (single, like a neutral).
    prod_me = prod_d[..., pid]
    prod_opp = prod_d.sum(dim=-1) - prod_me
    # [v26] Real-hold truncation: produced_delta assumes holding to horizon (prod·(H−eta)).
    # prod_hold_frac (per-candidate = min(H−eta,hold)/(H−eta) from deterministic hold(x))
    # scales it to the turns actually kept. Scales both my gain and opponent's loss.
    if prod_hold_frac is not None:
        phf = prod_hold_frac.to(prod_me.device)
        prod_me = prod_me * phf
        prod_opp = prod_opp * phf
    prod_full = prod_me - prod_opp
    if prod_mode is None:
        prod_score = prod_full
    else:
        pm = prod_mode.to(prod_full.device)
        prod_score = torch.where(pm == 1, prod_me, prod_full)   # 1=self_prod (drop opp loss)

    # Combat competitive diff (full): −(Δcomb_me − Σ_opp Δcomb_opp)
    #   net = produced − combat, so competitive combat contribution is the negative
    #   of (my combat minus opponents' combat).
    comb_me = comb_d[..., pid]
    comb_opp = comb_d.sum(dim=-1) - comb_me
    combat_full = -(comb_me - comb_opp)             # what "full" mode adds
    combat_self = -comb_me                          # only my own losses count

    # [v31] combat_scale (per-candidate, ∈[0,1]) attenuates the combat-cost term. Used for
    # the 4P suppression discount (用户验证方向): 我清敌garrison的战损成本 × (1 − 该敌方占比).
    # 打"占全场敌方实力大头"的主敌 → scale→0 → 战损≈不计(对冲, 削主威胁不是做嫁衣); 打苟活小
    # 虾米 → scale→1 → 全额战损(打它=替强敌清场做嫁衣)。这是 self(全1) 与 none(全0) 之间按
    # "做嫁衣比例"的精确插值, 零魔法值(占比纯对局状态算出)。仅作用于 combat 项, prod 项不变。
    if combat_scale is not None:
        cs = combat_scale.to(combat_self.device)
        combat_self = combat_self * cs
        combat_full = combat_full * cs

    if isinstance(combat_mode, str):
        if combat_mode == "none":
            return prod_score
        if combat_mode == "self":
            return prod_score + combat_self
        return prod_score + combat_full             # "full"

    # Tensor mode: per-candidate selection (0=full, 1=none, 2=self)
    cm = combat_mode.to(prod_score.device)
    combat_term = torch.where(cm == 1, torch.zeros_like(combat_full),
                  torch.where(cm == 2, combat_self, combat_full))
    return prod_score + combat_term


def score_candidates(
    status: PlanetGarrisonStatus,
    *,
    prod: Tensor,
    alive_by_step: Tensor,
    player_count: int,
    launches: LaunchSet,
    player_id: int,
    combat_mode: Tensor | str = "full",
    prod_mode: Tensor | None = None,
    prod_hold_frac: Tensor | None = None,
    combat_scale: Tensor | None = None,
) -> Tensor:
    """Competitive score per candidate. ``[C]`` (or scalar if no candidate axis).

    Uses the sparse exact flow projector. ``combat_mode`` selects ship-loss accounting;
    ``prod_mode`` full-double vs self-only production; ``prod_hold_frac`` truncates
    production to the real expected hold (see ``competitive_score``). ``combat_scale``
    (per-candidate ∈[0,1]) attenuates the combat-cost term (4P suppression discount).
    """
    diff = sparse_launch_flow_delta(
        status,
        prod=prod,
        alive_by_step=alive_by_step,
        player_count=int(player_count),
        launches=launches,
        player_id=int(player_id),
    )
    return competitive_score(diff, player_id=int(player_id), combat_mode=combat_mode,
                             prod_mode=prod_mode, prod_hold_frac=prod_hold_frac,
                             combat_scale=combat_scale)


# ---------------------------------------------------------------------------
# Candidate generation + greedy selection (P3: single-source, single-k, attack)
# ---------------------------------------------------------------------------



# Selection on CPU and CUDA must agree exactly: `torch.topk` / `torch.argmax`
# break ties differently across devices, and this planner ranks by integer ship
# counts / proximity that tie constantly — so device-stable selection is what
# keeps batch-CUDA play identical to CPU. We break ties by ascending slot index
# on both devices via a stable sort / lowest-index argmax.


def _stable_topk_indices(ranked: Tensor, k: int) -> Tensor:
    """Indices of the top-``k`` along the last dim, ties broken by ascending index
    identically on CPU and CUDA (stable descending sort)."""
    order = torch.argsort(ranked, dim=-1, descending=True, stable=True)
    return order[..., :max(1, int(k))]


def _stable_argmax(scores: Tensor) -> Tensor:
    """Lowest-index argmax along the last dim, device-deterministic on ties."""
    C = int(scores.shape[-1])
    is_max = scores == scores.max(dim=-1, keepdim=True).values
    idx = torch.arange(C, device=scores.device).expand_as(scores)
    return torch.where(is_max, idx, torch.full_like(idx, C)).argmin(dim=-1)


def _candidate_indices(values: Tensor, mask: Tensor, cap: int) -> tuple[Tensor, Tensor]:
    """Top-``cap`` slot indices of ``values`` under ``mask``. ``([K] long, [K] bool)``.

    Device-stable (ascending-index tie-break) — see note above.
    """
    p_count = values.shape[0]
    k = p_count if cap <= 0 else min(int(cap), p_count)
    neg_inf = torch.full_like(values, float("-inf"))
    ranked = torch.where(mask, values, neg_inf)
    top_idx = _stable_topk_indices(ranked, max(1, k))
    top_vals = ranked[top_idx]
    return top_idx, top_vals > float("-inf")


def is_comet_planet(obs_tensors: dict, P: int, device: torch.device) -> Tensor | None:
    """Per-slot mask of active comet planets, or ``None`` if absent."""
    comet_ids = obs_tensors.get("comet_planet_ids")
    if comet_ids is None:
        comets = obs_tensors.get("comets") or {}
        comet_ids = comets.get("planet_ids")
    planets = obs_tensors.get("planets")
    if comet_ids is None or planets is None:
        return None
    planet_ids = planets[..., 0].long()                       # [P]
    comet_ids = comet_ids.to(device=device).reshape(-1)
    mask = torch.zeros(P, dtype=torch.bool, device=device)
    for c in range(int(comet_ids.shape[-1])):
        cid = comet_ids[c]
        mask = mask | ((planet_ids == cid) & (cid >= 0))
    return mask


def reinforcement_timing_factor(eta: Tensor, *, eta_free: float, eta_scale: float) -> Tensor:
    """[v30] 兼容性死函数 (v26 起本体已被 enemy_reinforcement_schedule 取代, 不再调用)。
    保留仅为: arena 同进程对战时, 旧版本(v0-v28)的 main.py 会 import 它; 若 orbit_lite 包名串到
    本版而本版没有此符号 → 旧对手 ImportError → 空动作变植物人 → 污染跨版本(尤其4P)测试。
    保留空壳即可让旧对手 import 成功 (踩过, 见 kaggle_glob_pitfall)。"""
    scale = max(float(eta_scale), 1e-6)
    return ((eta - float(eta_free)) / scale).clamp(0.0, 1.0)


def capture_floor(
    garrison_status: PlanetGarrisonStatus,
    *,
    target_idx: Tensor,        # [T] long
    k_max: int,
    capture_overhead: float,
    player_id: int,
    reinforcement: Tensor | None = None,   # [T, K'>=K] float; added before ceil
) -> Tensor:
    """Owner-aware send floor per target at arrival turn ``k``. ``[T, K]``.

    [v43] 用 pre_combat_ships/owner 取代 post_combat. **关键 bug 修复** (replay 79934996 t58):
    do-nothing 投影里我自己已发射的 fleet 会让目标星 post_combat owner=me, 导致 floor=1
    (而 post_combat ships 是 combat 后我的残留, 很小). r0 = sizes - 1 严重高估我落地后的兵力,
    score 把"打中立 + 反扑"的候选误判为"白送". 用 pre_combat 才反映"我落地前要清的真实 garrison".

    - pre_combat owner == me → 我已占, floor=1 (无需清防, arrivals 加 garrison)
    - pre_combat owner != me → 真实 capture, floor = ceil(pre_combat_defenders + overhead + extra)

    ``reinforcement`` (optional, ``[T, K' ≥ K]``) is added to the defender count before the ceil
    on capture cells (not on ``mine_at_k`` reinforcement cells).

    Assumes ``k_max <= H``.
    """
    # [v43] 用 pre_combat_ships/owner; 若没有 (旧 movement) fallback 到 post_combat
    pre_ships = getattr(garrison_status, "pre_combat_ships", None)
    pre_owner = getattr(garrison_status, "pre_combat_owner", None)
    if pre_ships is not None and pre_owner is not None:
        ships = pre_ships
        owner = pre_owner
    else:
        ships = garrison_status.ships
        owner = garrison_status.owner
    dtype = ships.dtype if ships.is_floating_point() else torch.float32
    T = target_idx.shape[0]
    H_axis = int(ships.shape[-1])
    P = int(ships.shape[0])
    K = max(0, min(int(k_max), H_axis - 1))
    if K == 0:
        return torch.empty(T, 0, dtype=dtype, device=ships.device)
    tgt = target_idx.clamp(min=0, max=max(P - 1, 0))
    gathered = ships[tgt].to(dtype=dtype)                       # [T, H+1]
    owner_g = owner[tgt]                                        # [T, H+1]
    k_idx = torch.arange(1, K + 1, device=ships.device).view(1, K).expand(T, K)
    defenders = gathered.gather(-1, k_idx)                      # [T, K] pre-combat at k
    mine_at_k = owner_g.gather(-1, k_idx) == int(player_id)     # pre-combat owner check
    if reinforcement is not None:
        assert reinforcement.shape[-1] >= K, (
            f"reinforcement last dim {reinforcement.shape[-1]} < capture_floor K={K}"
        )
        extra = reinforcement[..., :K].to(dtype=dtype, device=ships.device)
    else:
        extra = 0.0
    arrivals_by_owner = getattr(garrison_status, "arrivals_by_owner", None)
    if arrivals_by_owner is not None:
        # Fleets that hit the target on the same step as our candidate fight in
        # the engine's fleet-vs-fleet bucket before the surviving attacker fights
        # the planet garrison.  They therefore must be included in the capture
        # floor for that exact arrival step; future-departure reinforcement only
        # covers not-yet-launched sources and does not include these in-flight
        # same-step arrivals.
        arr = arrivals_by_owner[tgt][:, : K + 1, :]                              # [T,K+1,A]
        A = int(arr.shape[-1])
        if int(player_id) < A:
            friendly_same_step = arr[:, 1 : K + 1, int(player_id)]
            other_arrivals = arr[:, 1 : K + 1, :].clone()
            other_arrivals[..., int(player_id)] = 0.0
        else:
            friendly_same_step = torch.zeros(T, K, dtype=arr.dtype, device=arr.device)
            other_arrivals = arr[:, 1 : K + 1, :]
        # Our candidate joins the player bucket at this same step.  To survive
        # fleet-vs-fleet and then fight the garrison, it only has to exceed the
        # strongest non-player owner bucket; other opponents do not stack.
        enemy_same_step = other_arrivals.max(dim=-1).values
        extra = extra + (enemy_same_step - friendly_same_step).to(dtype=dtype)
    cap = (defenders + float(capture_overhead) + extra).clamp(min=1.0).ceil()
    return torch.where(mine_at_k, torch.ones_like(cap), cap)


def attack_target_mask(obs, obs_tensors: dict) -> Tensor:
    """Enemy ∪ neutral, alive, non-comet. ``[P]`` bool."""
    mask = (obs.is_enemy | obs.is_neutral) & obs.alive
    comet = is_comet_planet(obs_tensors, obs.P, obs.device)
    if comet is not None:
        mask = mask & ~comet
    return mask


def friendly_flip_targets(
    obs, garrison_status: PlanetGarrisonStatus, *, H: int, prod: Tensor,
) -> tuple[Tensor, Tensor]:
    """Own planets the do-nothing projection shows flipping to an enemy within H — admitted
    to the defensive shortlist, competing in the SAME ROI pool as offence. The post-combat
    projection already encodes "enemy in-flight AND punches through" (strict net-threat).
    [v29] tried widening to "any enemy inbound" → over-defended, −8pp (30局×3对手), reverted.
    Returns ``(mask, urgency)``; urgency ≈ ships at stake = ``prod·(H−flip)+garrison``."""
    P = obs.P
    device = obs.device
    pid = int(obs.player_id)
    if H <= 0:
        z = torch.zeros(P, device=device)
        return torch.zeros(P, dtype=torch.bool, device=device), z
    owner_h = garrison_status.owner[..., 1:]                     # [P, H]
    flips = obs.owned.unsqueeze(-1) & (owner_h != pid)           # currently mine, not mine at some k
    any_flip = flips.any(dim=-1)                                 # [P]
    flip_turn = _stable_argmax(flips.to(torch.int64)) + 1        # 1-based earliest flip
    remaining = (float(H) - flip_turn.to(prod.dtype)).clamp(min=0.0)
    urgency = prod * remaining + obs.ships
    urgency = torch.where(any_flip, urgency, torch.full_like(urgency, float("-inf")))
    return any_flip, urgency


def build_target_shortlist(
    obs, obs_tensors, garrison_status, cache, *, config, K_eta, H, prod, source_mask,
):
    """Single unified shortlist: ``max_offensive_targets`` enemy/neutral targets by
    proximity ∪ ``max_defensive_targets`` friendly-flip targets by urgency., The
    two caps are independent (shortlist width == offensive + defensive), so each can
    be swept on its own. Returns ``(target_idx, target_exists)``."""
    P = obs.P
    device = obs.device
    n_attack = max(1, min(int(config.max_offensive_targets), P))
    R = max(0, min(int(config.max_defensive_targets), P))
    # [v29] tried UNIFIED-16 (drop the fixed 进攻12+防守4 split, let attack/defence compete
    # for one pool) → −13pp: defence ROI is systematically HIGHER (defends already-developed
    # low-cost stars), so a free pool over-defends and starves expansion. The fixed reserve
    # of attack slots is intentional — kept.
    attack_mask = attack_target_mask(obs, obs_tensors)
    proximity = min_distance_to_targets(cache, source_mask, attack_mask, max_k=K_eta)
    attack_pref = torch.where(attack_mask, -proximity, torch.full_like(proximity, float("-inf")))
    atk_idx, atk_exists = _candidate_indices(attack_pref, attack_mask, n_attack)

    if R > 0:
        flip_mask, urgency = friendly_flip_targets(obs, garrison_status, H=H, prod=prod)
        # Comets are temporary bodies.  Attack and regroup already exclude them
        # as destinations, and expiring owned comets are handled by the rescue
        # source logic; letting them occupy defensive slots can crowd out real
        # owned planets that are about to be captured.
        comet = is_comet_planet(obs_tensors, P, device)
        if comet is not None:
            flip_mask = flip_mask & ~comet
            urgency = torch.where(comet, torch.full_like(urgency, float("-inf")), urgency)
        # [v9] 4P abandon-outpost filter: don't defend low-production isolated planets
        # that are about to flip — save the garrison ships for better use elsewhere.
        # "Isolated" = fewer than 2 friendly planets within range 25.
        if hasattr(cache, 'cross_dist') and int(obs.owner_abs.max()) >= 2:  # 4P only
            d0 = cache.cross_dist[0]
            my_alive = obs.owned & obs.alive
            for p_idx in range(P):
                if not bool(flip_mask[p_idx]):
                    continue
                if float(prod[p_idx]) > 2:
                    continue  # high-production planets are worth defending
                # count friendly neighbours within 25 units
                dists = d0[p_idx]
                nearby = int(((dists < 25.0) & my_alive).sum().item()) - 1  # exclude self
                if nearby < 2:
                    # isolated + low prod → abandon (don't waste ships defending)
                    urgency[p_idx] = float("-inf")
                    flip_mask[p_idx] = False
        def_idx, def_exists = _candidate_indices(urgency, flip_mask, R)
        target_idx = torch.cat([atk_idx, def_idx], dim=0)
        target_exists = torch.cat([atk_exists, def_exists], dim=0)
    else:
        target_idx, target_exists = atk_idx, atk_exists
    return target_idx, target_exists


def reachable_mask(
    movement: PlanetMovement,
    *,
    source_idx: Tensor,      # [S] long
    target_idx: Tensor,      # [T] long
    fleet_sizes: Tensor,     # [S, T, G] float
    eta_cap: Tensor,         # [T] float (per-target reach cap)
    eps: float = 1e-4,
) -> Tensor:
    """Strict-superset reachability gate for the body screen, ``[S, T, G]`` bool.

    A cell is reachable iff some step interval ``k in [1, eta_cap[b,t]]`` admits the
    straight-line shot: ``(d_k - gap) <= fleet_speed(size) * k * (1 + eps)`` where
    ``d_k`` is the distance from the source centre @ turn 0 to the target's **swept
    segment** ``[tgt@(k-1), tgt@k]`` and ``gap = src_r + tgt_r + offsets``.

    Using the swept segment (not the point ``tgt@k``) and the surface gap makes this
    a provable *necessary condition* for ``intercept_angle`` viability: a viable shot
    contacts the target at some continuous ``t_c <= eta_cap`` with
    ``dist(src@0, tgt@t_c) - gap <= speed * t_c <= speed * ceil(t_c)``, and the
    segment distance over the interval containing ``t_c`` is ``<= dist(src@0, tgt@t_c)``.
    Hence ``viable => reachable`` (the ``eps`` absorbs fp32 boundary noise) — the gate
    never false-prunes a launch the agent would otherwise aim. ``intercept_angle``
    re-validates every survivor, so the surplus kept beyond true viability is harmless.
    """
    S, T, G = fleet_sizes.shape
    P = int(movement.P)
    dt = movement.dtype
    K = max(1, min(int(movement.movement_horizon), int(torch.ceil(eta_cap.max()).item())))
    src = source_idx.clamp(0, P - 1)
    tgt = target_idx.clamp(0, P - 1)

    # Source centre @ turn 0; target positions @ turns 0..K (segment endpoints).
    sx = movement.x[0][src].view(S, 1, 1)                                   # [S,1,1]
    sy = movement.y[0][src].view(S, 1, 1)
    tx = movement.x[: K + 1].gather(1, tgt.view(1, T).expand(K + 1, T))     # [K+1,T]
    ty = movement.y[: K + 1].gather(1, tgt.view(1, T).expand(K + 1, T))
    ax = tx[:K, :].view(1, K, T); ay = ty[:K, :].view(1, K, T)             # tgt@(k-1)
    bx = tx[1:, :].view(1, K, T); by = ty[1:, :].view(1, K, T)             # tgt@k

    # Point-to-segment distance from (sx,sy) to segment [(ax,ay),(bx,by)] → [S,K,T].
    abx = bx - ax; aby = by - ay
    apx = sx - ax; apy = sy - ay
    denom = (abx * abx + aby * aby).clamp(min=1e-12)
    u = ((apx * abx + apy * aby) / denom).clamp(0.0, 1.0)
    cx = ax + u * abx; cy = ay + u * aby
    seg_dist = torch.sqrt(((sx - cx) ** 2 + (sy - cy) ** 2).clamp(min=0.0))  # [S,K,T]

    src_r = movement.radii[src].view(S, 1, 1)
    tgt_r = movement.radii[tgt].view(1, 1, T)
    gap = src_r + tgt_r + (LAUNCH_SURFACE_OFFSET + TARGET_HIT_SURFACE_OFFSET)
    surf = (seg_dist - gap).clamp(min=0.0)                                   # [S,K,T]

    kv = torch.arange(1, K + 1, device=movement.device, dtype=dt).view(1, K, 1)
    ratio = surf / kv
    within = kv <= eta_cap.view(1, 1, T)                                    # [1,K,T]
    ratio = torch.where(within, ratio, torch.full_like(ratio, float("inf")))
    min_ratio = ratio.amin(dim=1)                                          # [S,T]

    speed = fleet_speed(fleet_sizes.clamp(min=1.0))                          # [S,T,G]
    reachable = min_ratio.unsqueeze(-1) <= speed * (1.0 + float(eps))        # [S,T,G]
    distinct = (src.view(S, 1) != tgt.view(1, T)).unsqueeze(-1)             # [S,T,1]
    return reachable & distinct


def _owned_continuation_value(
    *,
    movement: PlanetMovement,
    obs,
    obs_tensors: dict,
    garrison_status,
    staging_value: Tensor,
    ship_source: Tensor,
    config,
    t_max: float,
) -> Tensor:
    """Value of using an owned planet as a self-flow launchpad.

    High-score 2P stalemates show a lot of self->self circulation: ships land on
    an owned planet and are launched again shortly after.  This helper gives an
    owned planet A credit when A can make a short, still-owned next hop to an
    owned planet B that already has concrete next-wave value.  It is route-based
    (continuous aim + arrival owner check), not pressure propagation.
    """
    P = int(obs.P)
    device = obs.device
    dtype = ship_source.dtype
    mine = obs.owned & obs.alive
    comet = is_comet_planet(obs_tensors, P, device)
    if comet is not None:
        mine = mine & ~comet
    stage = staging_value.to(device=device, dtype=dtype).clamp(min=0.0)
    endpoint_mask = mine & (stage > float(config.regroup_pressure_delta_min))
    if not bool(mine.any()) or not bool(endpoint_mask.any()):
        return torch.zeros(P, dtype=dtype, device=device)

    src_idx = torch.nonzero(mine, as_tuple=True)[0]
    dst_idx = torch.nonzero(endpoint_mask, as_tuple=True)[0]
    S = int(src_idx.shape[0])
    T = int(dst_idx.shape[0])
    ships = ship_source[src_idx.clamp(0, P - 1)].to(dtype).clamp(min=1.0)
    active = reachable_mask(
        movement,
        source_idx=src_idx,
        target_idx=dst_idx,
        fleet_sizes=ships.view(S, 1, 1).expand(S, T, 1),
        eta_cap=torch.full((T,), float(t_max), dtype=dtype, device=device),
    ).squeeze(-1)
    aim = intercept_angle(
        movement,
        src_idx.view(S, 1),
        dst_idx.view(1, T),
        ships.view(S, 1),
        active=active,
    )
    eta = aim["eta"]
    owner = garrison_status.owner
    H_axis = int(owner.shape[-1])
    dst_owner = owner[dst_idx.clamp(0, P - 1)]
    k = torch.ceil(eta).clamp(min=0, max=H_axis - 1).long()
    owner_at_k = dst_owner.view(1, T, H_axis).expand(S, T, H_axis).gather(
        -1, k.unsqueeze(-1)
    ).squeeze(-1)
    valid = (
        active
        & aim["viable"]
        & (eta <= float(t_max))
        & (src_idx.view(S, 1) != dst_idx.view(1, T))
        & (owner_at_k == int(obs.player_id))
    )
    endpoint_value = stage[dst_idx.clamp(0, P - 1)].view(1, T)
    score = torch.where(
        valid,
        endpoint_value / torch.sqrt(eta.clamp(min=1.0)),
        torch.full((S, T), float("-inf"), dtype=dtype, device=device),
    )
    best = score.max(dim=1).values
    out = torch.zeros(P, dtype=dtype, device=device)
    out[src_idx] = torch.where(torch.isfinite(best), best.clamp(min=0.0), torch.zeros_like(best))
    return out


def _owned_at_eta(
    owner: Tensor,
    dst_idx: Tensor,
    eta: Tensor,
    *,
    player_id: int,
    precise: bool = False,
) -> Tensor:
    """Return whether each destination is still owned at arrival.

    ``dst_idx`` is ``[T]`` and ``eta`` is ``[S,T]``.  Precise mode checks the
    whole path window up to arrival; otherwise it checks the arrival frame only.
    """
    if eta.numel() == 0:
        return torch.zeros_like(eta, dtype=torch.bool)
    H_axis = int(owner.shape[-1])
    k = torch.ceil(eta).clamp(min=0, max=H_axis - 1).to(torch.long)
    dst_owner = owner[dst_idx.clamp(0, int(owner.shape[0]) - 1)]
    within_horizon = torch.isfinite(eta) & (torch.ceil(eta) < float(H_axis))
    if precise:
        K_max = int(k.max()) if k.numel() > 0 else 0
        K_max = max(1, min(K_max + 1, H_axis - 1))
        owner_window = dst_owner[:, 1:K_max + 1]
        j_grid = torch.arange(K_max, device=eta.device).view(1, 1, K_max)
        within = j_grid < k.unsqueeze(-1)
        owner_w_b = (owner_window == int(player_id)).view(1, dst_idx.shape[0], K_max)
        ok = ((~within) | owner_w_b.expand(eta.shape[0], dst_idx.shape[0], K_max)).all(dim=-1)
    else:
        ok = dst_owner.unsqueeze(0).expand(eta.shape[0], dst_idx.shape[0], H_axis).gather(
            -1, k.unsqueeze(-1)
        ).squeeze(-1) == int(player_id)
    return ok & within_horizon


def _regroup_route_options(
    *,
    movement: PlanetMovement,
    obs,
    obs_tensors: dict,
    garrison_status,
    src_idx: Tensor,
    dst_idx: Tensor,
    regroup_cap: Tensor,
    can_send: Tensor,
    dst_exists: Tensor,
    route_gain: Tensor,
    route_need: Tensor,
    config,
    precise_owner: bool,
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor]:
    """Choose the best next step toward each regroup destination.

    For a desired source A and final owned target B, evaluate:
    - launch directly to B now;
    - launch to an owned relay C now, then C can launch to B at A->C arrival;
    - wait a few turns when future orbit geometry makes A->B better.

    The returned action is only this turn's next hop.  Waiting returns a finite
    score but ``launch_now == False`` so the source keeps its ships for the next
    turn's fresh route calculation.
    """
    P = int(obs.P)
    S = int(src_idx.shape[0])
    T = int(dst_idx.shape[0])
    device = obs.device
    dtype = regroup_cap.dtype
    pid = int(obs.player_id)
    owner = garrison_status.owner
    H_axis = int(owner.shape[-1])
    if S == 0 or T == 0:
        zst = torch.full((S, T), float("-inf"), dtype=dtype, device=device)
        zlt = torch.zeros((S, T), dtype=torch.long, device=device)
        z = torch.zeros((S, T), dtype=dtype, device=device)
        zb = torch.zeros((S, T), dtype=torch.bool, device=device)
        return zst, zlt, z, z, zb

    src_mat = src_idx.view(S, 1).expand(S, T)
    dst_mat = dst_idx.view(1, T).expand(S, T)
    ships_mat = regroup_cap.view(S, 1).expand(S, T).clamp(min=1.0)
    direct = intercept_angle(movement, src_mat, dst_mat, ships_mat)
    direct_eta = direct["eta"].to(dtype)
    direct_valid = (
        direct["viable"]
        & (src_mat != dst_mat)
        & can_send.view(S, 1)
        & dst_exists.view(1, T)
        & route_need
        & _owned_at_eta(owner, dst_idx, direct_eta, player_id=pid, precise=precise_owner)
    )
    route_gain_pos = route_gain.to(dtype).clamp(min=0.0)
    direct_cost = direct_eta.clamp(min=1.0)
    direct_score = torch.where(
        direct_valid,
        route_gain_pos / direct_cost,
        torch.full((S, T), float("-inf"), dtype=dtype, device=device),
    )
    best_score = direct_score
    best_dst = dst_mat.clone()
    best_angle = direct["angle"].to(dtype)
    best_eta = direct_eta
    launch_now = direct_valid.clone()

    relay_mask = obs.owned & obs.alive
    comet = is_comet_planet(obs_tensors, P, device)
    if comet is not None:
        relay_mask = relay_mask & ~comet
    relay_idx = torch.nonzero(relay_mask, as_tuple=True)[0]
    R = int(relay_idx.shape[0])
    if R > 0:
        relay_src = src_idx.view(S, 1).expand(S, R)
        relay_mid = relay_idx.view(1, R).expand(S, R)
        relay_ships = regroup_cap.view(S, 1).expand(S, R).clamp(min=1.0)
        first = intercept_angle(movement, relay_src, relay_mid, relay_ships)
        first_eta = first["eta"].to(dtype)
        first_valid = (
            first["viable"]
            & (relay_src != relay_mid)
            & can_send.view(S, 1)
            & _owned_at_eta(owner, relay_idx, first_eta, player_id=pid, precise=precise_owner)
        )
        eta2 = torch.full((S, R, T), float("inf"), dtype=dtype, device=device)
        ok2 = torch.zeros((S, R, T), dtype=torch.bool, device=device)
        first_turn = torch.ceil(first_eta).to(torch.long)
        for s in range(S):
            if not bool(can_send[s]):
                continue
            turns = torch.unique(first_turn[s][first_valid[s]])
            for d_t in turns.tolist():
                d = int(d_t)
                if d <= 0 or d >= int(movement.movement_horizon):
                    continue
                mid_src = relay_idx.view(R, 1).expand(R, T)
                final_dst = dst_idx.view(1, T).expand(R, T)
                mid_k = min(max(d, 0), H_axis - 1)
                mid_owned = owner[relay_idx.clamp(0, P - 1), mid_k] == pid
                mid_base = torch.where(
                    mid_owned,
                    garrison_status.ships[relay_idx.clamp(0, P - 1), mid_k].to(dtype).clamp(min=0.0),
                    torch.zeros(R, dtype=dtype, device=device),
                )
                # If A lands on C, the next launch can combine A's fleet with
                # C's then-available garrison/production.  This is the concrete
                # speed benefit of using a relay instead of keeping the same
                # force in one long, unresponsive flight.
                mid_ship_vec = (regroup_cap[s].to(dtype).clamp(min=1.0) + mid_base).clamp(min=1.0)
                mid_ships = mid_ship_vec.view(R, 1).expand(R, T)
                second = intercept_angle(
                    movement,
                    mid_src,
                    final_dst,
                    mid_ships,
                    launch_turn=d,
                )
                use_mid = (first_turn[s] == d) & first_valid[s]
                eta2[s, use_mid, :] = second["eta"].to(dtype)[use_mid, :]
                ok2[s, use_mid, :] = second["viable"][use_mid, :]

        first_total = first_eta.ceil().clamp(min=1.0).view(S, R, 1)
        total_eta = first_total + eta2
        final_owned = torch.zeros((S, R, T), dtype=torch.bool, device=device)
        for s in range(S):
            final_owned[s] = _owned_at_eta(
                owner,
                dst_idx,
                total_eta[s],
                player_id=pid,
                precise=False,
            )
        relay_mid_id = relay_idx.view(1, R, 1)
        relay_valid = (
            ok2
            & first_valid.view(S, R, 1)
            & final_owned
            & route_need.view(S, 1, T)
            & dst_exists.view(1, 1, T)
            & (relay_mid_id != src_idx.view(S, 1, 1))
            & (relay_mid_id != dst_idx.view(1, 1, T))
        )
        # Cost combines total commitment time and first safe landing time.  This
        # prefers breaking a long march through a safe owned relay when the final
        # route value is comparable.
        relay_cost = torch.sqrt((total_eta.clamp(min=1.0) * first_total.clamp(min=1.0)).clamp(min=1.0))
        relay_score_all = torch.where(
            relay_valid,
            route_gain_pos.view(S, 1, T) / relay_cost,
            torch.full((S, R, T), float("-inf"), dtype=dtype, device=device),
        )
        relay_score, best_r = relay_score_all.max(dim=1)
        s_ar = torch.arange(S, device=device).view(S, 1).expand(S, T)
        t_ar = torch.arange(T, device=device).view(1, T).expand(S, T)
        relay_total_eta = total_eta[s_ar, best_r.clamp(0, max(R - 1, 0)), t_ar]
        relay_is_shortcut = (~direct_valid) | (relay_total_eta <= direct_eta)
        relay_better = (relay_score > best_score) & relay_is_shortcut
        relay_first_dst = relay_idx[best_r.clamp(0, max(R - 1, 0))]
        relay_first_angle = first["angle"].to(dtype)[s_ar, best_r.clamp(0, max(R - 1, 0))]
        relay_first_eta = first_eta[s_ar, best_r.clamp(0, max(R - 1, 0))]
        best_score = torch.where(relay_better, relay_score, best_score)
        best_dst = torch.where(relay_better, relay_first_dst, best_dst)
        best_angle = torch.where(relay_better, relay_first_angle, best_angle)
        best_eta = torch.where(relay_better, relay_first_eta, best_eta)
        launch_now = torch.where(relay_better, relay_score_all[s_ar, best_r.clamp(0, max(R - 1, 0)), t_ar].isfinite(), launch_now)

    wait_max = max(0, min(int(config.max_waves_per_turn) // 2, int(movement.movement_horizon) - 1, H_axis - 2))
    if wait_max > 0:
        best_wait = torch.full((S, T), float("-inf"), dtype=dtype, device=device)
        for d in range(1, wait_max + 1):
            future = intercept_angle(movement, src_mat, dst_mat, ships_mat, launch_turn=d)
            total_eta = future["eta"].to(dtype) + float(d)
            future_valid = (
                future["viable"]
                & (src_mat != dst_mat)
                & can_send.view(S, 1)
                & dst_exists.view(1, T)
                & route_need
                & _owned_at_eta(owner, dst_idx, total_eta, player_id=pid, precise=False)
            )
            wait_score = torch.where(
                future_valid,
                route_gain_pos / total_eta.clamp(min=1.0),
                torch.full((S, T), float("-inf"), dtype=dtype, device=device),
            )
            best_wait = torch.maximum(best_wait, wait_score)
        wait_better = best_wait > best_score
        best_score = torch.where(wait_better, best_wait, best_score)
        launch_now = torch.where(wait_better, torch.zeros_like(launch_now), launch_now)

    return best_score, best_dst, best_angle, best_eta, launch_now


def _greedy_select(
    *, P, W, device, dtype, score, cand_src, cand_send, cand_angle, cand_eta,
    cand_active, cand_tgt_slot, cand_tgt_short, cand_is_def, source_budget,
    target_exists, roi_threshold, cand_delay=None, cand_fund_budget=None,
    rank_score=None, initial_held_src=None,
) -> tuple[LaunchEntries, Tensor, Tensor, Tensor]:
    """Masking-only greedy over [C, L] candidates: pick the best wave each iter,
    one per target, source-budget aware across all L contributors. Enforces the
    role mutex: a reinforced planet can't also be a source, and vice-versa.

    Delayed candidates (``cand_delay[c] > 0``) represent "hold the source for d
    turns, then launch". They are scored normally but, when selected, do NOT emit
    a launch this turn — they only reserve the source and target (so neither is
    used for an inferior immediate target). ``cand_fund_budget`` ([C], optional)
    overrides the affordability check for delayed candidates (future ships =
    budget + d*prod); if None, the current ``source_budget`` is used.
    """
    C, L = int(cand_src.shape[0]), int(cand_src.shape[1])
    target_taken = ~target_exists.clone()                                        # [T]
    defended = torch.zeros(P, dtype=torch.bool, device=device)                   # reinforced this turn
    used_src = torch.zeros(P, dtype=torch.bool, device=device)                   # contributed this turn
    if cand_delay is None:
        cand_delay = torch.zeros(C, dtype=torch.long, device=device)

    w_src = torch.zeros(W, L, dtype=torch.long, device=device)
    w_send = torch.zeros(W, L, dtype=dtype, device=device)
    w_angle = torch.zeros(W, L, dtype=dtype, device=device)
    w_eta = torch.ones(W, L, dtype=dtype, device=device)
    w_tgt = torch.zeros(W, L, dtype=torch.long, device=device)
    w_active = torch.zeros(W, L, dtype=torch.bool, device=device)

    if initial_held_src is None:
        held_src = torch.zeros(P, dtype=torch.bool, device=device)               # sources holding this turn
    else:
        held_src = initial_held_src.to(device=device, dtype=torch.bool).clone()
    held_tgt = torch.zeros_like(target_exists, dtype=torch.bool)                 # targets reserved by holds
    initial_source_budget = source_budget.clone()
    for w in range(W):
        # Inner loop: keep picking the best candidate; if it's a delayed (hold)
        # pick, reserve its source and re-pick — delayed picks don't consume a wave.
        best_c = None
        while True:
            taken_cand = target_taken[cand_tgt_short]                           # [C]
            budget_at = source_budget[cand_src]                                 # [C, L]
            # Affordability: immediate use current budget; delayed use future-budget.
            if cand_fund_budget is not None:
                _fund_at = cand_fund_budget.to(device=device, dtype=dtype)
                if _fund_at.dim() == 1:
                    _fund_at = _fund_at.view(C, 1)
                # ``cand_fund_budget`` is built once before greedy selection.
                # Earlier waves can already have spent from the same source, so
                # subtract that committed debit before admitting later delayed
                # holds. Otherwise an unfundable delay can reserve a source/target.
                if not os.environ.get("PRODUCER_NO_DELAY_FUND_SPENT_FIX"):
                    spent_at = (initial_source_budget[cand_src] - budget_at).clamp(min=0.0)
                    _fund_at = (_fund_at - spent_at).clamp(min=0.0)
                can_fund = ((cand_send <= _fund_at) | ~cand_active).all(dim=-1) # [C]
            else:
                can_fund = ((cand_send <= budget_at) | ~cand_active).all(dim=-1)
            tgt_used_as_src = used_src[cand_tgt_slot]                           # [C]
            contrib_defended = (defended[cand_src] & cand_active).any(dim=-1)   # [C]
            # A held source is reserved — it can't contribute to any other launch.
            contrib_held = (held_src[cand_src] & cand_active).any(dim=-1)       # [C]
            # [v30 BUGFIX] gate(score>roi_threshold)并入 mask: 旧版 mask 不含门槛, 用 ROI 排序
            # argmax 选出"ROI最高"候选后才查它的绝对 score>roi → 若 ROI 最高者恰好 score≤0(低成本
            # 低产出的星 ROI 虚高), 直接 break 放弃所有其它 score>0 候选 → 整轮发0波。对局实证: 27%
            # 的"发0波"步其实有正收益候选却没发。并入 mask 后 ROI 只在过门槛候选里排, 不再误 break。
            mask = (torch.isfinite(score) & (score > roi_threshold) & ~taken_cand & can_fund
                    & ~tgt_used_as_src & ~contrib_defended & ~contrib_held)
            # Ranking key: by default the absolute net score; if rank_score given (e.g. the
            # ROI ratio score/ships — net value PER ship committed), pick by that instead so
            # the greedy prefers high-efficiency waves (more stars per fixed fleet budget).
            _rank = score if rank_score is None else rank_score
            masked_rank = torch.where(mask, _rank, torch.full_like(_rank, float("-inf")))
            cand = _stable_argmax(masked_rank)
            # mask 已含门槛 → 若无候选过门槛, masked_rank 全 -inf, argmax 任取一个但其 mask=False
            if not bool(mask[cand]):
                best_c = None
                break
            # Delayed pick: the best (source, delay) for this target wins it — hold
            # that source and claim the target so no OTHER source wastes effort on
            # the same target (they should go do something else). The target is not
            # attacked THIS turn; the held source launches once its ships accumulate.
            if int(cand_delay[cand].item()) > 0:
                _hold_src = cand_src[cand]
                _hm = torch.zeros(P, dtype=torch.long, device=device)
                _hm.scatter_add_(0, _hold_src, cand_active[cand].to(torch.long))
                held_src = held_src | (_hm > 0)
                target_taken[cand_tgt_short[cand]] = True
                held_tgt[cand_tgt_short[cand]] = True
                continue
            best_c = cand
            break

        if best_c is None:
            break

        sel_src = cand_src[best_c]                   # [L]
        sel_send = cand_send[best_c]
        sel_active = cand_active[best_c]
        w_src[w] = sel_src
        w_send[w] = torch.where(sel_active, sel_send, torch.zeros_like(sel_send))
        w_angle[w] = cand_angle[best_c]
        w_eta[w] = cand_eta[best_c]
        w_tgt[w] = cand_tgt_slot[best_c]
        w_active[w] = sel_active

        # debit all contributors' sends from their source budgets.
        debit = torch.zeros_like(source_budget)
        debit.scatter_add_(0, sel_src, torch.where(sel_active, sel_send, torch.zeros_like(sel_send)))
        source_budget = (source_budget - debit).clamp(min=0.0)
        # mark target taken (one wave per target).
        target_taken[cand_tgt_short[best_c]] = True
        # role mutex bookkeeping: mark contributors used; mark reinforced targets
        # defended. Sum active marks per planet (order-independent) and OR them in.
        src_mark = torch.zeros(P, dtype=torch.long, device=device)
        src_mark.scatter_add_(0, sel_src, sel_active.to(torch.long))
        used_src = used_src | (src_mark > 0)
        sel_tgt = cand_tgt_slot[best_c]
        sel_is_def = bool(cand_is_def[best_c])
        defended[sel_tgt] = defended[sel_tgt] | sel_is_def

    # Flatten waves x contributors into a LaunchEntries table.
    WL = W * L
    entries = LaunchEntries(
        source_slots=w_src.reshape(WL),
        target_slots=w_tgt.reshape(WL),
        ships=torch.where(w_active, w_send, torch.zeros_like(w_send)).reshape(WL),
        angle=torch.where(w_active, w_angle, torch.zeros_like(w_angle)).reshape(WL),
        eta=torch.where(w_active, w_eta, torch.ones_like(w_eta)).reshape(WL),
        valid=w_active.reshape(WL),
    )
    return entries, source_budget, held_src, held_tgt   # source_budget = leftover ships per planet


def plan_iterative_waves(
    *,
    movement: PlanetMovement,
    obs_tensors: dict,
    player_id: int,
    H: int,
    W: int,
    device, dtype,
    # candidate tables (shared across waves, built by the caller)
    cand_src, cand_send, cand_angle, cand_eta, cand_active, cand_tgt_slot,
    cand_tgt_short, cand_is_def, cand_delay, cand_src_prod,
    target_idx, target_exists,
    init_budget,            # [P] starting per-planet ship budget (obs.ships)
    init_score,             # [C] initial bonus-applied score
    roi_threshold: float,
    rescore_fn,             # (garrison_status, alive_by_step) -> [C] bonus-applied score
    rank_by_roi: bool = False,  # [v26] rank greedy by net-value-per-ship instead of abs net
    cand_cost=None,         # [v27] [C] real fleet to take the star (ROI denom; max(send,floor))
    rank_value=None,        # [v59] optional [C] value used only for ranking; score still gates
) -> tuple[LaunchEntries, Tensor, Tensor]:
    """[v25] Iterative multi-wave greedy, moved here from the agent shell (was v19).

    Repeatedly calls ``_greedy_select(W=1)``; between waves it applies the chosen
    launch to a movement deepcopy, rebuilds the garrison projection, and re-scores
    all remaining candidates via ``rescore_fn`` (a caller callback that owns the
    strategy bonuses — kept in the shell so this stays pure mechanism). A fired-but-
    uncaptured target is kept active so a later wave can pile another (nearer) source
    on it (v22 multi-source convergence). Returns
    ``(wave_entries, leftover_budget, held_sources)``.

    Mechanism only — no strategy. The single behavioural contract vs the old inline
    shell loop is byte-exactness, verified by per-game replay diff.
    """
    import copy as _copy
    P = int(init_budget.shape[0])
    C, L = int(cand_src.shape[0]), int(cand_src.shape[1])
    pid = int(player_id)

    all_wave_entries: list[LaunchEntries] = []
    source_budget = init_budget.clone()
    target_exists_iter = target_exists.clone()
    mov_iter = None
    score_iter = init_score
    _inflight_ships = torch.zeros(P, device=device, dtype=dtype)  # [v52] 每个星球已承诺在途兵力
    held_sources = torch.zeros(P, dtype=torch.bool, device=device)

    for _w in range(W):
        # Future-budget for affordability: delayed candidates spend current_budget +
        # delay * source_prod (ships accumulated while holding).
        _src_prod_CL = cand_src_prod
        if _src_prod_CL.dim() == 1:
            _src_prod_CL = _src_prod_CL.view(C, 1).expand(C, L)
        cand_fund_budget = source_budget[cand_src.clamp(0, P - 1)] + cand_delay.to(dtype).view(C, 1) * _src_prod_CL
        # [v26] ROI-ratio ranking key: net value per ship committed = score / Σships. Lets the
        # greedy prefer efficient waves (more captures per fixed fleet) over big-but-costly ones.
        _rank_score = None
        if rank_by_roi:
            # [v27] ROI denominator = real fleet to TAKE the star = max(single-source send,
            # capture floor). For single-source-sufficient stars this is the send; for high-
            # defence stars needing convergence it's the floor (total cross-source commitment)
            # → the multi-strike plan competes on (n+x)·m / (s_atk+s_friend), not on a single
            # source's tiny ROI (用户). Falls back to send-sum if cost unavailable.
            if cand_cost is not None:
                # [v52] 扣减已承诺在途兵力: 前波已投入 N 兵 → 实际还需 cost-N 即可拿下
                _tgt_global = target_idx[cand_tgt_short.clamp(min=0)].clamp(0, P - 1)
                _inflight_at_tgt = _inflight_ships[_tgt_global]
                _ships_c = (cand_cost - _inflight_at_tgt).clamp(min=1.0)
            else:
                _ships_c = cand_send.sum(dim=-1).clamp(min=1.0)
            if rank_value is not None:
                # Strategy shell can provide a context-specific ranking value
                # while keeping score_iter as the fire gate. Non-positive custom
                # values fall back to the current score.
                _rv = torch.where(rank_value > 0, rank_value, score_iter)
                _rank_score = _rv / _ships_c
            else:
                _rank_score = score_iter / _ships_c
        entry, source_budget, held_src, held_tgt = _greedy_select(
            P=P, W=1, device=device, dtype=dtype, score=score_iter,
            cand_src=cand_src, cand_send=cand_send, cand_angle=cand_angle, cand_eta=cand_eta,
            cand_active=cand_active, cand_tgt_slot=cand_tgt_slot, cand_tgt_short=cand_tgt_short,
            cand_is_def=cand_is_def, source_budget=source_budget,
            target_exists=target_exists_iter, roi_threshold=roi_threshold,
            cand_delay=cand_delay, cand_fund_budget=cand_fund_budget,
            rank_score=_rank_score,
            initial_held_src=held_sources,
        )
        held_sources = held_sources | held_src
        target_exists_iter = target_exists_iter & ~held_tgt
        if not bool(entry.valid.any()):
            break
        all_wave_entries.append(entry)

        fired_tgt = entry.target_slots[entry.valid]
        fired_slot = int(fired_tgt[0].item()) if fired_tgt.numel() > 0 else -1

        if mov_iter is None:
            mov_iter = _copy.deepcopy(movement)
        entry_d = disambiguate_duplicate_launches(entry)
        launch_p = infer_planned_launches_from_entries(
            obs_tensors=obs_tensors, movement=mov_iter, entries=entry_d, player_id=pid,
        )
        apply_private_planned_launches(
            movement=mov_iter, launches=launch_p, owner_id=pid, obs_tensors=obs_tensors,
        )
        gs_iter = mov_iter.garrison_status(max_horizon=H)
        abs_iter = mov_iter.alive_by_step[: H + 1]

        # Multi-source convergence: drop the target only if actually captured.
        if fired_slot >= 0:
            # [v52] 累计本波发往该目标的兵力
            _fv = entry.valid
            _ft = entry.target_slots[_fv]
            _fs = entry.ships[_fv]
            _inflight_ships.scatter_add_(0, _ft.clamp(0, P - 1).long(), _fs.to(dtype))

            tidx = (target_idx == fired_slot).nonzero(as_tuple=False)
            if tidx.numel() > 0:
                ti = int(tidx[0].item())
                if bool(gs_iter.owner[fired_slot, -1].item() == pid):
                    target_exists_iter[ti] = False
                    _inflight_ships[fired_slot] = 0.0  # captured, clear

        score_iter = rescore_fn(gs_iter, abs_iter)

    wave_entries = concat_launch_entries(all_wave_entries) if all_wave_entries else _empty_entries(device, dtype)
    return wave_entries, source_budget, held_sources


def _plan_regroup(
    *, movement, obs, obs_tensors, garrison_status, leftover, original_ships,
    pressure, config, H, pressure_raw=None, source_pending=None, staging_value=None,
    source_hold=None, source_reserve=None, support_need=None, support_value=None,
    support_horizon: float | None = None, target_bias=None,
) -> LaunchEntries:
    """Route-aware marshalling of leftover ships.

    Moves safe-drainable ships from low-value owned planets toward higher-value
    owned planets.  For 2P, the destination is a final intent B, but the action
    may be direct A->B, a first hop A->C where C can continue to B, or no launch
    when waiting for orbit phase is better.  This replaces the old fixed
    ``max_regroup_time`` cutoff as the main regroup reach rule.
    """
    import os as _os
    _T_OVR = _os.environ.get("PRODUCER_REGROUP_T")
    _PRECISE = _os.environ.get("PRODUCER_REGROUP_PRECISE") is not None
    _T_max = float(_T_OVR) if _T_OVR is not None else float(config.max_regroup_time)

    P = obs.P
    device = obs.device
    dtype = original_ships.dtype
    pid = int(obs.player_id)
    min_send = float(config.min_ships_to_launch)

    src_mask = obs.owned & obs.alive & (leftover >= min_send)
    if source_hold is not None:
        src_mask = src_mask & ~source_hold
    _gate_pending_by_stage = source_pending is not None and staging_value is not None
    if source_pending is not None and not _gate_pending_by_stage:
        # [v35] 有 attack 候选但没 fire 的源星 → 留兵等下回合, 不参与 regroup。
        src_mask = src_mask & ~source_pending
    if not bool(src_mask.any()):
        return _empty_entries(device, dtype)
    S_cap = max(1, min(int(config.max_regroup_sources_per_lane), P))
    src_idx, src_exists = _candidate_indices(leftover, src_mask, S_cap)          # rank by leftover
    S = int(src_idx.shape[0])
    leftover_s = leftover[src_idx.clamp(0, P - 1)]
    orig_s = original_ships[src_idx.clamp(0, P - 1)]
    # [v35 改动 b 已证伪 2026-06-12] 短 H_eff 反向放大 drain (safe_drain 数学: 窗口越短约束越少)
    # → regroup 黑洞化吸光 attack 资源 → 4P 31→16% 退化。保持 H_eff = full horizon。
    H_eff = torch.full((), float(H), dtype=dtype, device=device)
    reserve_s = None
    if source_reserve is not None:
        reserve_s = source_reserve.to(device=device, dtype=dtype)[src_idx.clamp(0, P - 1)].clamp(min=0.0)
    drain_s = safe_drain(
        garrison_status, source_idx=src_idx, source_ships=orig_s,
        H_eff=H_eff, player_id=pid, reserve=reserve_s,
        source_prod=obs.prod[src_idx.clamp(0, P - 1)].to(dtype),
    )
    committed_s = (orig_s - leftover_s).clamp(min=0.0)
    regroup_cap = torch.minimum(leftover_s, (drain_s - committed_s).clamp(min=0.0)).floor()
    can_send = src_exists & (regroup_cap >= min_send)
    if not bool(can_send.any()):
        return _empty_entries(device, dtype)

    # Destinations are owned, alive, non-comet planets (do-nothing projection).
    dst_mask = obs.owned & obs.alive
    comet = is_comet_planet(obs_tensors, P, device)
    if comet is not None:
        dst_mask = dst_mask & ~comet
    T_cap = max(1, min(int(config.max_regroup_targets_per_source), P))
    stage_route_value = None
    if staging_value is not None:
        _stage_base = staging_value.to(device=device, dtype=dtype).clamp(min=0.0)
        _cont = _owned_continuation_value(
            movement=movement,
            obs=obs,
            obs_tensors=obs_tensors,
            garrison_status=garrison_status,
            staging_value=_stage_base,
            ship_source=original_ships.to(dtype).clamp(min=min_send),
            config=config,
            t_max=_T_max,
        )
        stage_route_value = torch.maximum(_stage_base, _cont)
    dst_rank = pressure
    if stage_route_value is not None:
        dst_rank = dst_rank + stage_route_value
    dst_idx, dst_exists = _candidate_indices(dst_rank, dst_mask, T_cap)
    T = int(dst_idx.shape[0])

    # Keep target choice identical to the old regroup layer: a final target B is
    # eligible only if direct A->B was a valid regroup intent under the normal
    # regroup radius/ladder.  The route layer below may only change this turn's
    # next hop toward that already-selected B.
    regroup_active = reachable_mask(
        movement,
        source_idx=src_idx,
        target_idx=dst_idx,
        fleet_sizes=regroup_cap.view(S, 1, 1).expand(S, T, 1),
        eta_cap=torch.full((T,), _T_max, dtype=dtype, device=device),
    ).squeeze(-1)
    aim = intercept_angle(
        movement,
        src_idx.unsqueeze(1),
        dst_idx.unsqueeze(0),
        regroup_cap.unsqueeze(1),
        active=regroup_active,
    )
    eta = aim["eta"]
    viable = aim["viable"]

    src_pres = pressure[src_idx.clamp(0, P - 1)].view(S, 1)
    dst_pres = pressure[dst_idx.clamp(0, P - 1)].view(1, T)
    gap = dst_pres - src_pres                                                    # [S, T] (eff - eff, score用)
    stage_gain = torch.zeros_like(gap)
    if stage_route_value is not None:
        _stage = stage_route_value
        _src_stage = _stage[src_idx.clamp(0, P - 1)].view(S, 1)
        _dst_stage = _stage[dst_idx.clamp(0, P - 1)].view(1, T)
        stage_gain = (_dst_stage - _src_stage).clamp(min=0.0)
    support_gain = torch.zeros_like(gap)
    if support_need is not None and support_value is not None:
        # Concrete rescue support can open a regroup action. Reserve/preposition
        # signals are handled below as target bias only.
        _need = support_need.to(device=device, dtype=dtype).clamp(min=0.0)
        _value = support_value.to(device=device, dtype=dtype).clamp(min=0.0)
        _dst_need = _need[dst_idx.clamp(0, P - 1)].view(1, T)
        _dst_value = _value[dst_idx.clamp(0, P - 1)].view(1, T)
        _fill_frac = torch.minimum(regroup_cap.view(S, 1), _dst_need) / _dst_need.clamp(min=1.0)
        _h = float(support_horizon) if support_horizon is not None else float(H)
        _time_frac = ((_h - eta).clamp(min=0.0) / max(_h, 1.0)).to(dtype)
        support_gain = torch.where(
            _dst_need > 0.0,
            _fill_frac * _dst_value * _time_frac,
            torch.zeros_like(gap),
        )
    bias_gain = torch.zeros_like(gap)
    if target_bias is not None:
        _bias = target_bias.to(device=device, dtype=dtype).clamp(min=0.0)
        bias_gain = _bias[dst_idx.clamp(0, P - 1)].view(1, T).expand(S, T)
    # [v35] pressure_raw 提供时, filter 用 raw_gap (真敌方实力差) 防多源汇聚成黑洞;
    # score 仍用 eff gap (近邻中转站不被远端终点站盖过, 配合 eta 罚项形成链式中继)。
    if pressure_raw is not None:
        _src_raw = pressure_raw[src_idx.clamp(0, P - 1)].view(S, 1)
        _dst_raw = pressure_raw[dst_idx.clamp(0, P - 1)].view(1, T)
        gap_filter = _dst_raw - _src_raw                                          # [S, T]
    else:
        gap_filter = gap

    src_neq_dst = src_idx.view(S, 1) != dst_idx.view(1, T)
    pressure_ok = gap_filter > float(config.regroup_pressure_delta_min)
    stage_ok = stage_gain > float(config.regroup_pressure_delta_min)
    support_ok = support_gain > float(config.regroup_pressure_delta_min)
    regroup_need = pressure_ok | stage_ok | support_ok

    owner = garrison_status.owner
    H_axis = int(owner.shape[-1])
    dst_owner = owner[dst_idx.clamp(0, P - 1)]
    k = torch.ceil(eta).clamp(min=0, max=H_axis - 1).to(torch.long)
    if _PRECISE:
        K_max = int(k.max()) if k.numel() > 0 else 0
        K_max = max(1, min(K_max + 1, H_axis - 1))
        owner_window = dst_owner[:, 1:K_max + 1]
        j_grid = torch.arange(K_max, device=device).view(1, 1, K_max)
        within = j_grid < k.unsqueeze(-1)
        owner_w_b = (owner_window == pid).view(1, T, K_max).expand(S, T, K_max)
        still_mine = ((~within) | owner_w_b).all(dim=-1)
    else:
        still_mine = dst_owner.unsqueeze(0).expand(S, T, H_axis).gather(
            -1, k.unsqueeze(-1)
        ).squeeze(-1) == pid

    base_valid = (
        viable & still_mine & src_neq_dst
        & regroup_need
        & can_send.view(S, 1) & dst_exists.view(1, T)
    )
    if _gate_pending_by_stage:
        # Pending attack sources should not be drained by pure pressure moves, but
        # they may still muster toward a strictly better next-wave launchpad.
        _pending_s = source_pending[src_idx.clamp(0, P - 1)].view(S, 1)
        base_valid = base_valid & ((~_pending_s) | (stage_gain > 0.0))

    if _os.environ.get("PRODUCER_REGROUP_LADDER", "1") == "1":
        _radii = [5.0, 10.0, 15.0, 20.0]
        eta_cap_per_src = torch.full((S,), _radii[-1], device=device, dtype=eta.dtype)
        _resolved = torch.zeros(S, dtype=torch.bool, device=device)
        for _r in _radii:
            _has = (base_valid & (eta <= _r)).any(dim=1)
            _newly = _has & (~_resolved)
            eta_cap_per_src = torch.where(
                _newly,
                torch.full_like(eta_cap_per_src, _r),
                eta_cap_per_src,
            )
            _resolved = _resolved | _has
        valid = base_valid & (eta <= eta_cap_per_src.view(S, 1))
    else:
        valid = base_valid & (eta <= _T_max)

    # Marginal fill: when a destination already holds a large garrison, another
    # regroup wave has lower marginal value. Keep staging linear because moving
    # toward a launchpad is a route/setup action, while pressure/support/bias are
    # direct force-fill signals.
    _dst_ships = original_ships[dst_idx.clamp(0, P - 1)].to(dtype).view(1, T).clamp(min=0.0)
    _fill_cap = regroup_cap.view(S, 1).to(dtype)
    _marginal_fill = (_fill_cap / (_dst_ships + _fill_cap).clamp(min=1.0)).clamp(min=0.0, max=1.0)
    target_value = stage_gain + (gap + support_gain + bias_gain) * _marginal_fill
    target_score = target_value - float(config.regroup_time_penalty_weight) * eta
    route_need = valid
    route_gain = target_value.clamp(min=0.0)
    route_score, route_dst, route_angle, route_eta, launch_now = _regroup_route_options(
        movement=movement,
        obs=obs,
        obs_tensors=obs_tensors,
        garrison_status=garrison_status,
        src_idx=src_idx,
        dst_idx=dst_idx,
        regroup_cap=regroup_cap,
        can_send=can_send,
        dst_exists=dst_exists,
        route_gain=route_gain,
        route_need=route_need,
        config=config,
        precise_owner=_PRECISE,
    )
    # Route planning answers "how do I move toward this already-valued target?"
    # It must not re-rank B by travel efficiency; otherwise the route layer turns
    # into a new regroup target formula and over-pulls ships into easy self-flow.
    sc = torch.where(
        valid & torch.isfinite(route_score),
        target_score,
        torch.full_like(target_score, float("-inf")),
    )
    best_t = _stable_argmax(sc)                                                  # [S] device-stable
    best_score = sc.gather(-1, best_t.unsqueeze(-1)).squeeze(-1)                 # [S]
    best_launch_now = launch_now.gather(-1, best_t.unsqueeze(-1)).squeeze(-1)
    best_valid = torch.isfinite(best_score) & best_launch_now
    s_ar = torch.arange(S, device=device)
    best_dst = route_dst[s_ar, best_t]                                           # [S]
    best_angle = route_angle[s_ar, best_t]
    best_eta = route_eta[s_ar, best_t]
    if _os.environ.get("PRODUCER_ROUTE_LOG"):
        import sys as _sys
        _step = int(obs.step.reshape(-1)[0].item()) if hasattr(obs.step, "reshape") else -1
        _lo = int(_os.environ.get("PRODUCER_ROUTE_LOG_START", "0"))
        _hi = int(_os.environ.get("PRODUCER_ROUTE_LOG_END", "999"))
        if _lo <= _step <= _hi:
            _has_score = torch.isfinite(best_score)
            _direct = _has_score & best_launch_now & (best_dst == dst_idx[best_t])
            _relay = _has_score & best_launch_now & (best_dst != dst_idx[best_t])
            _wait = _has_score & ~best_launch_now
            _no = ~_has_score
            _ships = regroup_cap.to(dtype)
            def _sum(mask):
                return float(_ships[mask].sum().item()) if bool(mask.any()) else 0.0
            print(
                "ROUTE "
                f"step={_step} src={S} direct={int(_direct.sum())}/{_sum(_direct):.0f} "
                f"relay={int(_relay.sum())}/{_sum(_relay):.0f} "
                f"wait={int(_wait.sum())}/{_sum(_wait):.0f} no={int(_no.sum())} "
                f"launched={int(best_valid.sum())}/{_sum(best_valid):.0f}",
                file=_sys.stderr,
            )
            _route_log_file = _os.environ.get("PRODUCER_ROUTE_LOG_FILE")
            if _route_log_file:
                with open(_route_log_file, "a") as _fh:
                    print(
                        "ROUTE "
                        f"step={_step} src={S} direct={int(_direct.sum())}/{_sum(_direct):.0f} "
                        f"relay={int(_relay.sum())}/{_sum(_relay):.0f} "
                        f"wait={int(_wait.sum())}/{_sum(_wait):.0f} no={int(_no.sum())} "
                        f"launched={int(best_valid.sum())}/{_sum(best_valid):.0f}",
                        file=_fh,
                    )

    return LaunchEntries(
        source_slots=src_idx,
        target_slots=best_dst,
        ships=torch.where(best_valid, regroup_cap, torch.zeros_like(regroup_cap)),
        angle=torch.where(best_valid, best_angle, torch.zeros_like(best_angle)),
        eta=torch.where(best_valid, best_eta, torch.ones_like(best_eta)),
        valid=best_valid,
    )


def _empty_entries(device: torch.device, dtype: torch.dtype) -> LaunchEntries:
    z = torch.zeros(0, dtype=dtype, device=device)
    zl = torch.zeros(0, dtype=torch.long, device=device)
    return LaunchEntries(
        source_slots=zl, target_slots=zl, ships=z, angle=z, eta=z,
        valid=torch.zeros(0, dtype=torch.bool, device=device),
    )


def entries_to_sparse_payload(entries: LaunchEntries, *, planet_ids: Tensor) -> dict[str, Tensor]:
    """Convert a LaunchEntries table to the sparse action-row payload."""
    L = entries.source_slots.shape[0]
    device = entries.source_slots.device
    P = int(planet_ids.shape[0])
    valid_long = entries.valid.to(torch.int64)
    counts = valid_long.sum().to(torch.int32)
    max_count = int(counts.item())
    out_from = torch.full((max_count,), -1, dtype=torch.int32, device=device)
    out_angle = torch.zeros((max_count,), dtype=torch.float32, device=device)
    out_ships = torch.zeros((max_count,), dtype=torch.float32, device=device)
    if max_count == 0:
        return {"from_planet_id": out_from, "angle": out_angle, "num_ships": out_ships, "counts": counts}
    safe_src = entries.source_slots.clamp(min=0, max=max(P - 1, 0))
    from_pid_full = planet_ids[safe_src].to(torch.int32)
    launch_rank = valid_long.cumsum(0) - valid_long
    l_idx = torch.where(entries.valid)[0]
    pos = launch_rank[l_idx]
    out_from[pos] = from_pid_full[l_idx]
    out_angle[pos] = entries.angle[l_idx].to(torch.float32)
    out_ships[pos] = entries.ships[l_idx].to(torch.float32)
    return {"from_planet_id": out_from, "angle": out_angle, "num_ships": out_ships, "counts": counts}


def empty_action_row(device: torch.device) -> dict[str, Tensor]:
    """Sparse launch payload with zero launches."""
    return {
        "from_planet_id": torch.full((0,), -1, dtype=torch.int32, device=device),
        "angle": torch.zeros((0,), dtype=torch.float32, device=device),
        "num_ships": torch.zeros((0,), dtype=torch.float32, device=device),
        "counts": torch.zeros((), dtype=torch.int32, device=device),
    }


def safe_drain(
    garrison_status: PlanetGarrisonStatus,
    *,
    source_idx: Tensor,            # [S] long — planet slots to evaluate
    source_ships: Tensor,          # [S] float — current garrison at those slots
    H_eff: Tensor,                 # scalar float — horizon to protect the source over
    player_id: int = 0,
    reserve: Tensor | None = None,  # [S] float — defensive garrison to keep back
    source_prod: Tensor | None = None,  # [S] float — production for exact recheck
) -> Tensor:
    """Max ships a source can shed while staying held over ``H_eff``. ``[S]``.

    Closed form, no scoring. For every source slot, over the turns ``t = 1..H``
    where the do-nothing projection still has us holding the planet (``owner == me``,
    ``ships > 0``) within ``H_eff``, the largest amount we can remove now while the
    projected garrison stays non-negative on every such turn is
    ``min_t(ships_traj[t])`` — leaving the planet at 0 ships on the worst held turn
    is allowed. Capped by ``source_ships`` (can't send more than we hold now):

        safe_drain = clamp(min(min_t held(ships_traj), source_ships) - reserve, 0)

    ``reserve`` ([S], optional) is a per-source defensive floor kept back against
    *potential* (not-yet-launched) enemy attacks — the do-nothing trajectory only
    accounts for enemy fleets already in transit, so without a reserve a source with
    no visible threat would be drained to 0 and fall to a freshly-launched attack.

    A source that cannot be continuously held through ``H_eff`` and never
    recovers has nothing stable to protect, so reserve is skipped for it (no
    point holding back ships on a planet the projection says we lose anyway).
    Transient breaks that recover later are not drained: friendly in-flight
    support may be relying on the current garrison to bridge a one-frame gap.
    """
    S = source_idx.shape[0]
    ships_cache = garrison_status.ships
    dtype = ships_cache.dtype if ships_cache.is_floating_point() else torch.float32
    device = ships_cache.device

    H_axis = int(ships_cache.shape[-1])
    H = max(H_axis - 1, 0)
    P = int(ships_cache.shape[0])
    if H == 0:
        return torch.zeros(S, dtype=dtype, device=device)

    src_idx_safe = source_idx.clamp(min=0, max=max(P - 1, 0))

    src_ships_traj = ships_cache[src_idx_safe][..., 1:].to(dtype=dtype)          # [S, H]
    src_owner_traj = garrison_status.owner[src_idx_safe][..., 1:]                 # [S, H]
    me_owned = src_owner_traj == int(player_id)

    turn_grid = torch.arange(1, H + 1, device=device, dtype=dtype).view(1, H)
    within_horizon = turn_grid <= H_eff                                          # H_eff scalar

    held = me_owned & within_horizon & (src_ships_traj > 0.0)
    inf_fill = torch.full_like(src_ships_traj, float("inf"))
    cap_traj = torch.where(held, src_ships_traj, inf_fill)
    min_slack = cap_traj.min(dim=-1).values                                       # [S]
    drain = torch.minimum(min_slack, source_ships.to(dtype))
    if reserve is not None:
        # Default keeps v67 semantics: engine ownership survives a 0-garrison
        # non-capture frame and owned 0-garrison planets still produce next step,
        # so a global "leave 1 ship" margin is not objectively required and
        # panel-regressed.  The stricter recovery/margin behavior remains opt-in
        # for replay experiments only.
        if os.environ.get("PRODUCER_STRICT_SAFE_DRAIN_RESERVE"):
            not_held = within_horizon & ~held
            broke = not_held.any(dim=-1)
            seen_break = torch.cumsum(not_held.to(torch.int64), dim=-1) > 0
            recovers_after_break = (seen_break & held).any(dim=-1)
            unrecovered = broke & ~recovers_after_break
            hold_floor = torch.maximum(reserve.to(dtype), torch.ones_like(drain))
            protected_drain = (drain - hold_floor).clamp(min=0.0)
            drain = torch.where(
                unrecovered,
                drain,
                torch.where(recovers_after_break, torch.zeros_like(drain), protected_drain),
            )
        else:
            doomed = torch.isinf(min_slack)
            drain = torch.where(doomed, drain, drain - reserve.to(dtype))
    if not os.environ.get("PRODUCER_NO_EXACT_SAFE_DRAIN") and source_prod is not None:
        arrivals = getattr(garrison_status, "arrivals_by_owner", None)
        if arrivals is not None:
            H_guard = max(0, min(H, int(torch.floor(H_eff.detach()).item())))
            if H_guard > 0:
                owner_guard = garrison_status.owner[src_idx_safe, 1 : H_guard + 1]
                lost = owner_guard != int(player_id)
                seen_lost = torch.cumsum(lost.to(torch.int64), dim=-1) > 0
                recovers_after_loss = ((owner_guard == int(player_id)) & seen_lost).any(dim=-1)
                needs_exact = recovers_after_loss & (torch.floor(drain) > 0.0)
                if bool(needs_exact.any()):
                    exact_pos = torch.where(needs_exact)[0]
                    exact_drain = _exact_safe_drain_owner_cap(
                        garrison_status=garrison_status,
                        arrivals_by_owner=arrivals,
                        source_idx=src_idx_safe[exact_pos],
                        source_ships=source_ships.to(dtype)[exact_pos],
                        source_prod=source_prod.to(device=device, dtype=dtype)[exact_pos],
                        drain=drain[exact_pos],
                        H_guard=H_guard,
                        player_id=int(player_id),
                    )
                    drain = drain.clone()
                    drain[exact_pos] = exact_drain
    return drain.clamp(min=0.0)


def _exact_safe_drain_owner_cap(
    *,
    garrison_status: PlanetGarrisonStatus,
    arrivals_by_owner: Tensor,
    source_idx: Tensor,
    source_ships: Tensor,
    source_prod: Tensor,
    drain: Tensor,
    H_guard: int,
    player_id: int,
) -> Tensor:
    """Tighten drain only when engine-style replay says recovery would degrade.

    This preserves v67's useful "0-garrison owned planets may still produce"
    semantics.  It only lowers a source cap if sending the candidate amount would
    make a transiently-lost source fail to recover on a frame where the no-action
    projection had recovered ownership.
    """
    device = drain.device
    dtype = drain.dtype
    out = drain.clone()
    A = int(arrivals_by_owner.shape[-1])
    if A <= 0:
        return out
    for i in range(int(source_idx.shape[0])):
        high = int(torch.floor(out[i]).item())
        if high <= 0:
            continue
        s = int(source_idx[i].item())
        baseline_owner = garrison_status.owner[s, 1 : H_guard + 1]
        protect = baseline_owner == int(player_id)
        if not bool(protect.any()):
            continue
        lost = baseline_owner != int(player_id)
        if not bool(lost.any()):
            continue
        seen_lost = torch.cumsum(lost.to(torch.int64), dim=0) > 0
        recover_protect = protect & seen_lost
        if not bool(recover_protect.any()):
            continue

        arr = arrivals_by_owner[s, 1 : H_guard + 1].to(device=device, dtype=dtype)
        prod_i = float(source_prod[i].item())
        ships0 = float(source_ships[i].item())
        owner0 = int(garrison_status.owner[s, 0].item())

        def _ok(send_n: int) -> bool:
            owner = owner0
            ships = max(0.0, ships0 - float(send_n))
            for k in range(H_guard):
                if owner >= 0:
                    ships += prod_i
                step_arr = arr[k]
                if A >= 2:
                    top2 = torch.topk(step_arr, k=2)
                    top_ships = float(top2.values[0].item())
                    second_ships = float(top2.values[1].item())
                    survivor_owner = int(top2.indices[0].item())
                    survivor_ships = 0.0 if top_ships == second_ships else max(0.0, top_ships - second_ships)
                else:
                    top_ships = float(step_arr[0].item())
                    survivor_owner = 0
                    survivor_ships = max(0.0, top_ships)
                if survivor_ships > 0.0:
                    if owner == survivor_owner:
                        ships += survivor_ships
                    else:
                        diff = ships - survivor_ships
                        if diff < 0.0:
                            owner = survivor_owner
                            ships = -diff
                        else:
                            ships = diff
                if bool(recover_protect[k].item()) and owner != int(player_id):
                    return False
            return True

        if _ok(high):
            continue
        lo = 0
        hi = high
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _ok(mid):
                lo = mid
            else:
                hi = mid - 1
        out[i] = torch.minimum(out[i], torch.tensor(float(lo), dtype=dtype, device=device))
    return out
