# 技术设计

## 架构总览

```text
Arena ──POST /matches──> Match(training|ranked) ──worker──> ReplayArtifact
  │                             │                            │
  └── /match/:id ──poll GET─────┴──── replay ready ─────────┘

Strategy Lab ──save draft──> StrategyDraft(revision)
     │                             │
     ├──simulate──> Match(mode=training) + candidate attribution
     │                             │
     ├──workspace poll <── persisted validation_simulation_match_id
     │                             │
     └──publish ──server gate──────┘

Public history/replay ── exclude any match carrying candidate attribution
Replay ──fromReplay──> public compact summary ──> Strategy Lab source card
```

## 功能列表

1. candidate simulation 的持久关联、私有可见性与发布门禁。
2. 公共历史、公开舰队档案和公开 replay 的权威分类与隐私过滤。
3. Arena 创建后的比赛专属状态页与 replay 直达。
4. replay 到 Strategy Lab 的最小来源上下文。
5. start 页舰队状态语义、双语标题和账户菜单鉴权文案。

## 共享基础

### 比赛底层 mode 与产品展示分类

现有 `MatchMode`、Contracts 和 worker 只接受 `training | ranked`，rating 也只认 `ranked`。本期不新增 `strategy_simulation` mode，避免破坏协议和历史数据。

产品展示分类由以下规则确定：

- 任一参赛记录存在 `candidate_content_hash`：`strategy_simulation`。
- 否则使用 `Match.mode` 的 `training` 或 `ranked`。
- 无法识别：`unknown`，公共查询不返回，前端不回退为排位赛。

“私人”是可见性，不是 mode。candidate simulation 始终私人；普通 training 仍按现有公开 replay 规则展示。

### candidate simulation 判定

在 API 查询中使用针对 `MatchParticipant.candidate_content_hash IS NOT NULL` 的 `EXISTS`/`NOT EXISTS` 条件，避免依赖 `matchmaking_reason` 或请求入口。worker 写 replay 时使用同一事实决定 `ReplayArtifact.is_public`。

### 状态映射

- 比赛状态沿用 `MatchStatus`：`queued/preparing/ready/running/finalizing/finished/failed/forfeited/cancelled`。
- Strategy Lab 对外把 `finished` 归一为 `completed`；其余进行态和失败态保持可解释映射。
- 发布资格永远由服务端重新读取当前 `StrategyDraft`、关联 `Match` 和 candidate participant 计算，前端状态只用于展示。

## 功能：candidate simulation 持久关联与发布门禁

### 涉及文件

- `services/api/orbit_api/db/models.py`
- `services/api/alembic/versions/0009_core_loop_trust.py`
- `services/api/orbit_api/domain/strategy_lab.py`
- `services/api/orbit_api/api/strategy_lab.py`
- `apps/web/src/api.ts`
- `apps/web/app/strategy-lab/StrategyLab.tsx`

### 类型 / 接口

`StrategyDraft` 新增：

- `validation_simulation_match_id: UUID | None`，外键指向 `matches.id`。
- `validation_simulation_revision: int | None`，记录发起模拟时的草稿 revision。

workspace 响应新增 `simulation`：

```text
publicId, kind=strategy_simulation, visibility=private,
status, result, replayPublicId, validationPassed,
publishEligible, blockingReason
```

### 函数 / 方法

- `attach_validation_simulation(...)`：模拟创建后把当前 revision 与 match 绑定到草稿。
- `publication_eligibility(...)`：校验 revision、内容 hash、match 终态与 candidate validation。
- `require_publishable_simulation(...)`：publish API 的服务端强制门禁。
- 草稿保存/重置时清空旧关联、验证 hash 与报告。

### 设计决策

**为什么不把 simulation ID 放在浏览器存储？**

刷新、切语言和跨设备恢复都需要服务端权威关联；浏览器存储无法保证 revision 一致性，也会引入过期发布资格。

**为什么单独保存 revision，还要校验 candidate hash？**

revision 提供直接关联，hash 防止错误关联或历史数据异常。两者都满足才可发布。

**何时解锁发布？**

关联 match 必须为 `FINISHED`，candidate validation 的 `result` 必须为 `ready`，且 hash 与当前草稿一致。`QUEUED/RUNNING/FAILED/未知/旧 revision` 均拒绝。

## 功能：公共历史与 replay 隐私

### 涉及文件

- `services/api/orbit_api/api/leaderboard.py`
- `services/api/orbit_api/api/replays.py`
- `services/match-worker/orbit_match_worker/replay/persistence.py`
- `apps/web/components/product/PublicCompetition.tsx`
- `apps/web/src/public-replay.ts`

### 与现有代码的关系

公共历史当前只按 `ReplayArtifact.is_public` 过滤，历史卡片又硬编码 `RANKED ENCOUNTER`。本期增加 candidate `NOT EXISTS` 过滤，并直接使用响应中的权威 `mode` 渲染训练/排位标签。

公共 fleet profile 同样过滤 candidate simulation；公开 replay 查询即使遇到历史上错误标记为公开的 candidate artifact，也返回 404，防止迁移前数据泄露。

worker 创建 replay 时：candidate simulation 使用 `is_public=False`，普通 training/ranked 保持现有行为。

## 功能：比赛状态追踪

### 涉及文件

- `services/api/orbit_api/api/matches.py`
- `apps/web/app/match/MatchStatusView.tsx`
- `apps/web/app/[locale]/[[...slug]]/page.tsx`
- `apps/web/app/arena/ArenaForm.tsx`
- `apps/web/src/api.ts`

### 接口

现有 `GET /api/v1/matches/{match_id}` 扩展返回：`result`、`createdAt`、`finishedAt`、`replayPublicId` 和参赛舰队名称。鉴权仍要求当前用户的舰队是参赛方。

### 页面行为

`/{locale}/match/{matchId}` 每 2 秒轮询进行态；保留 match ID，瞬时失败显示重试且不清空上下文。`finished + replay` 直达 replay；`finished + no replay` 显示回放生成中并继续刷新。Arena 的 Agent 路径创建成功后直接进入该页，不再进入 Command Center。

## 功能：replay 来源上下文

### 涉及文件

- `apps/web/app/strategy-lab/StrategyLab.tsx`
- `apps/web/src/public-replay.ts`

从 `fromReplay` 读取现有公开 compact replay。只在公共接口成功返回时展示卡片，包含 mode、胜负、双方、第一条已有事件或事实，以及精确返回链接。404/403/无效 ID 只显示不阻断操作的“来源不可用”，不保留上一次数据。

不新增高光算法，也不为私人 candidate replay 开公开读取口子。

## 功能：start 与账户菜单

### 涉及文件

- `apps/web/app/[locale]/[[...slug]]/page.tsx`
- `apps/web/app/start/StartFlow.tsx`
- `apps/web/components/product/SiteHeader.tsx`
- `apps/web/components/product/SessionAction.tsx`
- `apps/web/src/i18n.ts`

中文 start 标题使用中文。`StartFlow` 根据 session、fleet 与当前策略状态显示未登录、创建、继续配置或已就位状态；已有 ready 舰队的主 CTA 为 Arena，不重新呈现创建流程。

账户菜单复用 session 查询结果：仅已登录显示“退出登录 / Sign out”，未登录不渲染退出项。

## 方案对照与选择

| 方案 | 成本 | 兼容性 | 风险 |
| --- | --- | --- | --- |
| 给 `Match.mode` 新增 `strategy_simulation` | 高，需改 Contracts、worker、rating、迁移 | 差 | 历史和协议不兼容 |
| 保持 mode，按 candidate attribution 推导展示分类 | 低 | 高 | 查询必须统一使用 helper/条件 |

推荐第二种。最重要的考量是保持现有比赛执行与积分语义不变；代价是产品层需要区分“底层 mode”和“展示分类”。

## 技术验收标准

- 数据库从 0008 升到 0009，新增关联字段可回滚。
- candidate simulation 不出现在公共 matches、公共 fleet profile，公开 replay 读取返回 404；普通 training 仍显示 Training。
- workspace 在重载后恢复当前 revision 的 simulation；切换语言不丢状态。
- publish 在 queued/running/failed/stale/无关联时拒绝，只有 finished + ready validation + 当前 hash 成功。
- Match 状态 API 只对参赛用户可见，包含 replay readiness；Web 可从创建一路轮询到 replay。
- 有效公开 replay 显示来源卡片；无效/私人 replay 不泄露内容。
- start 与菜单在中英文、登录/未登录和 ready/未完成状态下符合产品表格。
- API/Web 聚焦测试、lint/typecheck 和相关构建通过。
