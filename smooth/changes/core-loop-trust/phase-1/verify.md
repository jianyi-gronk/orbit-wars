# 验证

验证日期：2026-07-19

## 结论

**通过。** Phase 1 的数据边界、服务端门禁、Web 核心链路、双语呈现和运行时韧性均已实现并获得自动化与真实浏览器证据。用户无需 Agent Key 即可从现有舰队进入竞技场，创建训练赛，追踪到完成状态和权威回放；平台内候选策略只有在当前草稿的私有模拟完成且固定验证通过后才能发布。

## 自动化证据

- [x] `pnpm check`：Prettier、ESLint、Ruff、TypeScript、mypy 全部通过。
- [x] JavaScript：Contracts 12 项、Design tokens 4 项、Web 64 项通过。
- [x] Python：180 项通过、5 项跳过；仅保留既有 Starlette/httpx 弃用警告。
- [x] `NEXT_PUBLIC_ORBIT_DEV_SUBJECT=local-commander ORBIT_HUMAN_PLAY_ENABLED=false pnpm --filter @orbit-wars/web build`：Next.js 16 生产构建通过。
- [x] SQLite migration：0001→0009、0009→0008、0008→0009 通过。
- [x] PostgreSQL migration：当前版本为 `0009 (head)`。

## 核心链路证据

- [x] Start：中英文标题正确；已有 `Aurora Veil` 时主行动为“进入竞技场 / Enter Arena”，并提供平台内优化入口，不要求 Agent Key。
- [x] Arena：创建训练赛 `match_zNkjDMlVeeBj-AMwScQET1tR`，状态页自动追踪至 `FINISHED`，约 6 秒后出现权威回放 `replay_z0CLwnl0XvLCHeOpm4MJkED0`。
- [x] Match status：展示权威 mode、双方名称、控制类型、完成结果和 replay readiness；`step_limit` 在中英文分别显示“回合上限 / Turn limit”。
- [x] Strategy Lab：候选模拟 `match_yNnZz16bFidEpMxeCuKZzfyx` 在排队/运行阶段保持发布禁用，`COMPLETED + validation passed` 后解锁；刷新与语言切换后状态仍存在。
- [x] Publish gate：服务端拒绝无关联模拟、旧 revision、未完成、失败和未通过验证的发布请求；客户端按钮仅为辅助提示。
- [x] Privacy：候选模拟与其 replay 默认私有；即使 legacy 数据误标为 public，公共 match、fleet profile 和 replay API 仍过滤/拒绝；浏览器公开历史不含候选 match ID。
- [x] Replay handoff：有效 replay 显示 mode、对阵、结果、最小高光和返回入口；无效 replay 清除旧上下文且不阻塞编辑。
- [x] History：Training/Ranked 按权威 `Match.mode` 双语显示，未知值不回退为 Ranked。
- [x] Session menu：已登录显示“退出登录 / Sign out”；未登录静态路径隐藏退出项。
- [x] Responsive：390×844 下比赛状态页长 ID 可换行，标题、状态卡和主按钮不再被横向裁切。

## 运行时恢复证据

- [x] 复现 Redis live-event `XADD` 超时导致整场比赛失败。
- [x] 修复后实时 snapshot/event 发布可降级，权威引擎、回放持久化和比赛结算继续执行。
- [x] Worker 在队列 `BLPOP` 暂时超时时保持进程存活并自动重试。
- [x] 修复后的真实训练赛成功完成，公开历史出现训练标签和永久回放。

## 保留讨论项

- 私人模拟未来分享的是 replay、结果还是策略，以及是否采用可撤销只读链接。
- 多场胜率发布门槛的最少场次、对手覆盖和统计稳定性。
- 已有舰队首页 CTA 是否根据最近任务动态切换“继续上场 / 优化策略”。
- 多舰队的默认舰队、策略归属和跨页面上下文。
- 世界观术语与直接功能术语的长期组合方式。
