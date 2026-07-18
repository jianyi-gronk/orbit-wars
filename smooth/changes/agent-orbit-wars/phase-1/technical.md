# 技术设计

## 设计状态

本设计面向第一阶段的公开互联网 2P 产品，覆盖人类与 Agent 共用规则、匹配池、排名和回放的完整闭环。当前工作区尚无应用代码，因此采用轻量多服务起步，但不引入 Kubernetes、事件溯源平台或多区域部署等超出第一阶段的问题。

## 架构总览

```text
┌──────────────────────────── Browser ────────────────────────────┐
│ Next.js Web                                                     │
│ 营销/档案/榜单 · PixiJS 战场 · DOM HUD · WebSocket 客户端       │
└───────────────┬───────────────────────────┬─────────────────────┘
                │ HTTPS / JSON              │ WSS + 短期比赛票据
                ▼                           ▼
┌──────────────────────── Python API ─────────────────────────────┐
│ 身份验证 · 舰队/版本 · Agent API · 匹配 · 排名 · 回放查询       │
│ WebSocket Gateway · 限流 · 短期比赛票据                         │
└───────────────┬───────────────────────────┬─────────────────────┘
                │ SQL                       │ Redis Streams/PubSub
                ▼                           ▼
        ┌──────────────┐             ┌────────────────────┐
        │ PostgreSQL   │             │ Match Worker        │
        │ 业务真相源   │             │ 权威时钟与引擎状态  │
        └──────────────┘             └───────┬────────────┘
                                             │ JSONL stdin/stdout
                            ┌────────────────┴───────────────┐
                            ▼                                ▼
                    Agent Sandbox A                  Agent Sandbox B
                    无网络/限时/只读                  或 Human Adapter

        ┌────────────────────────────────────────────────────────┐
        │ Object Storage：策略包、压缩回放、回放快照、公开素材   │
        └────────────────────────────────────────────────────────┘
```

### 推荐部署单元

- `apps/web`：Next.js 前端与服务端渲染，只做展示和 API 客户端，不持有游戏规则。
- `services/api`：FastAPI 控制面、REST API、Agent API 和 WebSocket 网关。
- `services/match-worker`：长生命周期比赛执行、权威时钟、引擎调用和回放写入。
- `services/agent-sandbox`：固定协议的隔离执行镜像，不直接对公网暴露。
- PostgreSQL：用户、舰队、版本、比赛、排名与幂等记录。
- Redis：实时命令流、帧广播、队列、在线状态和速率限制；不作为最终真相源。
- S3 兼容对象存储：不可变策略包、回放与媒体。

## 功能列表

1. 共享协议、身份和数据基础
2. 规则引擎与确定性比赛
3. 人类/Agent 统一控制与实时对局
4. Agent 接入、版本发布与沙箱
5. 匹配、统一排名与反刷分
6. 回放、事件提取与战场渲染
7. 舰队、账号和公开档案
8. 原创视觉系统与无障碍
9. 运行、监控与故障恢复

## 关键方案对照

### 应用架构

| 方案 | 成本 | 优点 | 主要问题 |
|---|---:|---|---|
| 全部放进 Next.js | 低 | 单仓单服务 | 无法安全、稳定地运行 Python 引擎和任意 Agent 代码 |
| Next.js + Python API/Worker | 中 | 贴合现有 Python 引擎，Web 与比赛职责清楚 | 多一个部署语言和契约生成步骤 |
| 完整微服务/Kubernetes | 高 | 扩展边界最强 | 第一阶段运维过度设计 |

**推荐：Next.js + Python API/Worker。** 最重要的考量是复用现有引擎并隔离不可信 Agent。放弃的是单进程部署的简单性。

### 人类操作节奏

| 方案 | 兼容性 | 可玩性 | 风险 |
|---|---:|---:|---|
| 原始 1 秒窗口 | 高 | 低 | 人类难以稳定完成选择、瞄准和兵力输入 |
| 每 5 个引擎步一个宏回合 | 低 | 高 | 改变策略节奏，破坏现有 Agent 的逐步状态记忆 |
| 每引擎步 3 秒同步窗口 | 高 | 中高 | 极长局最多约 25 分钟 |

**推荐：每引擎步 3 秒同步窗口。** 120 份本地 2P 回放抽样中位为 178 步、75 分位为 213 步，对应约 9–11 分钟。保留逐步规则意味着现有 `agent(obs)` 可以直接适配；放弃的是极短的实时节奏。

### Agent 语言

| 方案 | 兼容性 | 安全/成本 | 策略自由度 |
|---|---:|---:|---:|
| Python 隔离容器 | 最高 | 中高 | 高 |
| JavaScript isolate | 低 | 中 | 高 |
| 受限策略 DSL | 无 | 低 | 低 |

**推荐：第一阶段支持固定依赖环境中的 Python `agent(obs)`。** 这样可以直接使用现有 `producer/v69` 和工具链。代价是必须建立真正的进程/容器隔离，而不能在 API 进程里 `import` 用户代码。

### 战场渲染

| 方案 | 结果质量 | 维护成本 | 结论 |
|---|---:|---:|---|
| 复用旧 Canvas renderer | 低 | 低 | 仅适合作为规则参考与测试 oracle |
| DOM/SVG | 中 | 中高 | 对大量移动对象和粒子效果不理想 |
| PixiJS/WebGL + DOM HUD | 高 | 中 | 推荐；战场高性能，信息层仍可访问 |

## 共享基础

### 目录规划

```text
apps/
  web/
    app/                       # 首页、竞技场、比赛、回放、档案、榜单
    components/battle/         # PixiJS 场景与 DOM HUD
    components/editorial/      # 时尚编辑式品牌组件
    lib/api/                   # 生成的 API 客户端
services/
  api/
    app/api/                   # REST、Agent API、WebSocket
    app/domain/                # 舰队、版本、比赛、排名业务
    app/db/                    # SQLAlchemy 模型与 Alembic
  match-worker/
    app/engine/                # 引擎适配、比赛状态机
    app/runtime/               # Human/Agent 控制器
    app/replay/                # 帧、事件、压缩与上传
  agent-sandbox/
    runner.py                  # JSONL 协议入口
packages/
  contracts/                  # JSON Schema、生成的 TypeScript 类型
  orbit-engine-py/            # 固定版本的规则引擎与测试
  design-tokens/              # 颜色、字体、间距、动效 token
infra/
  compose/                    # 本地 PostgreSQL/Redis/对象存储
  containers/                 # API、Worker、Sandbox 镜像
```

### 核心协议

所有跨进程协议使用带版本号的 JSON Schema。Python 端以 Pydantic 为源生成 Schema，再生成 TypeScript 类型；禁止前后端各自手写同名结构。

```ts
type ControllerType = "human" | "agent";
type MatchMode = "training" | "ranked";

interface PlanetV1 {
  id: number;
  owner: -1 | 0 | 1;
  x: number;
  y: number;
  radius: number;
  ships: number;
  production: number;
}

interface FleetV1 {
  id: number;
  owner: 0 | 1;
  x: number;
  y: number;
  angle: number;
  fromPlanetId: number;
  ships: number;
}

interface ObservationV1 {
  schemaVersion: 1;
  matchId: string;
  step: number;
  player: 0 | 1;
  deadlineAt: string;
  angularVelocity: number;
  planets: PlanetV1[];
  fleets: FleetV1[];
  initialPlanets: PlanetV1[];
  comets: CometGroupV1[];
}

interface LaunchCommandV1 {
  fromPlanetId: number;
  angle: number;       // radians, normalized to [0, 2π)
  ships: number;       // positive integer
}

interface CommandBatchV1 {
  schemaVersion: 1;
  matchId: string;
  expectedStep: number;
  commands: LaunchCommandV1[];
  idempotencyKey: string;
}
```

引擎边界保留原始动作 `[[from_planet_id, angle, ships], ...]`，只在协议适配层转换，避免修改已有 Agent。

### 通用身份与 ID

- 数据库内部使用 UUID；公开链接使用不可枚举的 ULID/随机 ID。
- 用户会话使用 HttpOnly、Secure、SameSite Cookie；API 验证 OIDC JWT。
- Agent Key 采用 `owk_<public-prefix>_<secret>` 形式，只显示一次；数据库仅保存可索引前缀与密钥摘要。
- 所有写接口支持 `Idempotency-Key`，尤其是版本发布、模拟、挑战和排名结算。

### 核心数据表

```text
users
fleets                     # 一个舰队一个统一 rating 身份
agent_keys                 # scope、摘要、撤销时间、最近使用时间
strategy_versions          # 不可变包、hash、状态、submitted_by
matches                    # ruleset、seed、mode、状态、结果、replay_id
match_participants         # fleet、slot、controller_type、strategy_version
match_commands             # step、slot、命令摘要、提交时间、有效性
ratings                    # fleet_id、mu、sigma、display_score
rating_events              # match_id 幂等唯一、before/after/delta
replay_artifacts           # 对象存储 key、schema、checksum、公开状态
```

统一排名绑定 `fleet_id`，不绑定控制方式；人类和 Agent 只是 `match_participants.controller_type` 标签。

## 功能：规则引擎与确定性比赛

### 涉及文件

- `packages/orbit-engine-py/orbit_engine/engine.py`
- `packages/orbit-engine-py/orbit_engine/schema.py`
- `packages/orbit-engine-py/tests/test_golden_replays.py`
- `services/match-worker/app/engine/adapter.py`
- `services/match-worker/app/engine/state_machine.py`

### 与现有代码的关系

- 从已安装的 `kaggle_environments/envs/orbit_wars/orbit_wars.py` 与 JSON 规范提取并固定规则；该包为 Apache-2.0，复制时保留 License/NOTICE。
- 第一阶段规则锁定为网站自己的 `ruleset_id`，不在运行时依赖 Kaggle master 分支。
- 现有规则默认 `episodeSteps=500`、`shipSpeed=6.0`、`cometSpeed=4.0`；动作仍是源星 ID、弧度和舰船数。
- `env.step(actions)` 与 `env.toJSON()` 可作为迁移期 golden oracle，但生产 Worker 使用提取后的最小引擎包，避免加载整个 Kaggle 依赖树。
- 现有 `orbit_wars.js` 只作为坐标和表现参考，不直接进入新 UI。

### 接口

```py
class OrbitEngine(Protocol):
    def reset(self, *, seed: int, players: int = 2) -> EngineSnapshot: ...
    def step(self, actions: list[list[LaunchCommand]]) -> EngineStepResult: ...
    def snapshot(self, *, player: int | None = None) -> EngineSnapshot: ...
    @property
    def done(self) -> bool: ...

class RulesetRegistry:
    def get(self, ruleset_id: str) -> OrbitEngineFactory: ...
```

### 设计决策

**为什么提取固定引擎而不是直接升级 Kaggle 包？** 线上排名必须能够永久复现。每场比赛记录 `ruleset_id`、引擎 commit、seed、槽位和全部动作；升级只能新增 ruleset，不能改变旧 ruleset。

**seed 何时可见？** 比赛进行中仅 Worker 可见；结束后写入回放元数据，便于复现和争议审计。

**如何验证未改坏规则？** 选取现有测试、固定 seed 与历史 replay，逐步比较 planets、fleets、reward 和结束步，要求全量相等；浮点坐标使用明确容差并记录平台。

## 功能：统一控制与实时对局

### 涉及文件

- `services/api/app/api/ws_matches.py`
- `services/api/app/domain/match_tickets.py`
- `services/match-worker/app/runtime/controllers.py`
- `services/match-worker/app/runtime/turn_clock.py`
- `packages/contracts/schemas/live-match-v1.json`
- `apps/web/components/battle/use-match-socket.ts`

### 比赛状态机

```text
queued → preparing → ready → running → finalizing → finished
              └──────────────→ failed
running → forfeited → finalizing
queued/preparing → cancelled
```

- 只有 `finished` 或可归因玩家的 `forfeited` 排位赛可以结算分数。
- 基础设施故障进入 `failed`，不改变排名。
- `finalizing` 负责回放上传、事件提取和幂等排名结算。

### WebSocket 消息

```ts
type ServerMessage =
  | { type: "match.snapshot"; payload: ObservationV1 }
  | { type: "turn.open"; step: number; deadlineAt: string }
  | { type: "turn.accepted"; step: number; commandHash: string }
  | { type: "turn.closed"; step: number }
  | { type: "match.frame"; payload: ReplayFrameV1 }
  | { type: "match.finished"; result: MatchResultV1 }
  | { type: "match.error"; code: string; recoverable: boolean };

type ClientMessage =
  | { type: "turn.submit"; payload: CommandBatchV1 }
  | { type: "match.resync"; lastSeenStep: number };
```

### 回合规则

1. Worker 生成同一步的两个玩家视角快照。
2. `turn.open` 带服务端绝对截止时间；默认 3 秒，可由 ruleset 配置。
3. 人类通过 WebSocket 提交；Agent Sandbox 接收同一 Observation 并返回同一 CommandBatch。
4. 双方动作在截止前都不可被对方看见；截止后同时送入引擎。
5. 未提交视为 `[]`，不会复用上一回合动作。
6. 每回合最多 6 条 launch，重复源星的总舰船数不得超过当前库存。
7. Worker 推进恰好一个原始引擎步，广播权威 frame，然后打开下一回合。

Agent 与人类共享 3 秒逻辑截止；Agent 另有 1 秒 CPU 上限和累计 overage bank，防止通过重计算垄断资源。Agent-vs-Agent 可跳过真实等待并加速执行，但每一步的观察和动作边界保持相同，因此仍可进入统一排名。

### 输入校验

- `expectedStep` 必须等于当前开放 step；迟到或重放返回稳定错误码。
- `angle` 必须有限并规范化；`ships` 必须为正整数。
- 源星必须存在且当前属于提交者。
- 同源多发按提交顺序扣减预算；总数超出则整批拒绝，不做部分猜测。
- 服务端永远重新校验，前端轨迹预览不构成规则依据。

### 断线策略

- 浏览器使用短期 match ticket 重连，恢复时发送最新 snapshot 与后续 frame。
- 人类暂时断线时按空动作推进；连续错过 10 个窗口后判负。
- Agent 连续超时或累计 overage 耗尽时判负。
- Worker 崩溃从最近持久化快照和命令日志恢复；无法确定性恢复则比赛失败且不计分。

## 功能：Agent 接入、版本与沙箱

### 涉及文件

- `services/api/app/api/agent.py`
- `services/api/app/domain/strategy_versions.py`
- `services/match-worker/app/runtime/agent_executor.py`
- `services/agent-sandbox/runner.py`
- `services/agent-sandbox/Dockerfile`
- `packages/contracts/schemas/agent-api-v1.json`

### 外部 Agent API

```text
GET    /api/agent/v1/fleet
GET    /api/agent/v1/versions
POST   /api/agent/v1/versions
POST   /api/agent/v1/simulations
GET    /api/agent/v1/matches
GET    /api/agent/v1/opponents
POST   /api/agent/v1/challenges
GET    /api/public/v1/replays/{public_id}
```

- Bearer Key 绑定一支舰队并声明 `fleet:read`、`version:write`、`simulate`、`challenge` scopes。
- 创建版本需要 Python 包、`manifest.json`、版本说明和 `submittedBy`。
- 每个策略版本不可变，使用 SHA-256 内容 hash 去重并固定运行镜像版本。
- 发布流程为 `uploaded → validating → ready | rejected`；只有 `ready` 能参加正式战。

### Agent 运行协议

Sandbox 启动后通过 JSON Lines 通信：

```text
stdin : {"type":"observe","requestId":"...","observation":{...}}
stdout: {"type":"action","requestId":"...","commands":[...]}
```

入口保持：

```py
def agent(obs: dict) -> list[list[int | float]]:
    ...
```

因此 `submissions/producer/v69/main.py` 可作为专家内置 Bot；其 `obs.step=None` fallback 在网站环境不应触发，因为 Worker 始终发送真实 step。

### 沙箱边界

- 生产环境不在 API/Worker 进程内导入用户代码。
- 每位 Agent 独立非 root 容器/微虚机；禁网络、只读根文件系统、tmpfs 工作区。
- 固定 Python 与依赖镜像；限制 CPU、内存、进程数、文件大小、日志和墙钟时间。
- 不注入数据库、对象存储或平台密钥。
- 发布前执行解包安全检查、导入 smoke、固定 observation 合同测试和资源测试。
- 运行日志按步截断并默认私有；公开回放只暴露安全的错误类别，不暴露堆栈或源码。

### 设计决策

**为什么不允许任意 pip install？** 依赖下载会引入供应链、网络和不可复现问题。第一阶段提供固定依赖清单；新增依赖通过平台镜像升级。

**为什么不直接执行 AI 返回的代码？** AI 只负责提交一个待验证版本，验证通过后才进入不可变版本库，比赛永远引用具体版本 ID。

## 功能：匹配、统一排名与反刷分

### 涉及文件

- `services/api/app/domain/matchmaking.py`
- `services/api/app/domain/ratings.py`
- `services/api/app/domain/anti_abuse.py`
- `services/api/app/api/leaderboard.py`
- `services/api/app/db/models/rating.py`

### 接口

```py
class RatingService:
    def preview(self, match: FinishedMatch) -> RatingDelta: ...
    def apply_once(self, match_id: UUID) -> RatingEvent: ...

class Matchmaker:
    def find(self, fleet_id: UUID, controller: ControllerType) -> MatchOffer: ...
```

### 排名模型

- 每支舰队只有一组 `mu/sigma`，人类与 Agent 操作都更新这组值。
- 展示分使用保守分 `mu - k*sigma` 映射至段位，避免新号少量胜局直接冲榜。
- 第一阶段采用支持未来多人的 OpenSkill/Plackett-Luce 风格更新；领域层通过 `RatingService` 隔离具体库。
- 每场记录控制方式和策略版本，榜单可筛选分析，但不能产生另一套隐藏分。

### 公平与反刷

- 正式比赛只接受服务端生成 seed、随机槽位和当前 ruleset。
- 同一对手短时间重复对战逐步降低或停止分数变化。
- 对明显超出合理分差的定向挑战限制次数；正常匹配优先同段位和低重复度。
- 结算在 PostgreSQL 事务内完成，`rating_events.match_id` 唯一，保证重试不重复加分。
- 用户取消、平台故障和无法归因的引擎错误不计分；主动断线、超时和代码崩溃按判负处理。

## 功能：回放、事件与渲染

### 涉及文件

- `services/match-worker/app/replay/writer.py`
- `services/match-worker/app/replay/events.py`
- `services/api/app/api/replays.py`
- `packages/contracts/schemas/replay-v1.json`
- `apps/web/components/battle/BattleStage.tsx`
- `apps/web/components/battle/ReplayController.tsx`
- `apps/web/components/battle/scenes/*`

### 回放格式

```ts
interface ReplayV1 {
  schemaVersion: 1;
  match: {
    publicId: string;
    rulesetId: string;
    engineCommit: string;
    seed: number;
    participants: ReplayParticipantV1[];
    result: MatchResultV1;
  };
  initial: ReplayFrameV1;
  frames: ReplayFrameV1[];
  commands: ReplayCommandV1[];
  events: BattleEventV1[];
  checkpoints: ReplayCheckpointV1[];
}
```

- Worker 逐步写临时流，比赛结束后压缩上传，避免整局只保存在内存。
- 每 20 步保存 seek checkpoint；其间帧使用 delta 编码。
- 原始动作、权威状态和派生事件分层保存。事件提取器升级时可重算，不修改原始帧。
- 回放对象以 checksum 校验；公开 API 返回短期 CDN URL 或流式响应。

### 关键事件提取

- `planet_captured`
- `home_planet_lost`
- `largest_launch`
- `production_lead_changed`
- `ship_lead_changed`
- `player_eliminated`
- `agent_timeout` / `human_disconnect`
- `match_finished`

胜因说明只陈述可计算事实，例如“第 83 步后产能领先持续 40 步”，不由生成式模型臆测。

### 前端渲染

- PixiJS/WebGL 绘制太阳、星球、舰队、轨迹、彗星和粒子。
- DOM HUD 绘制兵力、归属、倒计时、控制方式、时间线和键盘可访问操作。
- 使用权威 frame 插值动画，不在客户端重算碰撞或胜负。
- 轨迹预览使用同一几何函数的 TypeScript 只读端口，但最终命中仍以服务器为准。
- `prefers-reduced-motion` 下关闭镜头推进、视差、扫描和排版错位，只保留必要状态变化。

## 功能：舰队、账号与公开档案

### 涉及文件

- `services/api/app/api/fleets.py`
- `services/api/app/domain/fleets.py`
- `services/api/app/domain/agent_keys.py`
- `apps/web/app/(app)/command/*`
- `apps/web/app/fleet/[slug]/*`

### REST API

```text
POST   /api/v1/fleets
GET    /api/v1/fleets/{id}
PATCH  /api/v1/fleets/{id}
POST   /api/v1/fleets/{id}/agent-keys
DELETE /api/v1/fleets/{id}/agent-keys/{key_id}
GET    /api/v1/fleets/{id}/versions
POST   /api/v1/matches
GET    /api/v1/matches/{id}
GET    /api/v1/leaderboard
```

- 第一阶段每个账号一支活跃舰队，由数据库唯一约束保证。
- 舰队名称、代号、宣言和外观描述经过长度、字符和内容安全检查。
- 公开档案只展示发布版本元数据，不默认公开源码或 Agent 日志。
- 历史版本“设为当前”只移动舰队指针，不修改历史版本。

## 功能：原创视觉系统

### 涉及文件

- `packages/design-tokens/tokens.css`
- `apps/web/components/editorial/*`
- `apps/web/components/navigation/*`
- `apps/web/styles/motion.css`
- `apps/web/app/(marketing)/*`

### 设计边界

- 品牌页采用非对称编辑网格、超大标题、满版视觉和轨道母题。
- 战斗页使用稳定的三层结构：全屏战场、操作 HUD、可收起的指标/事件层。
- 设计 token 区分 `editorial` 与 `tactical` 密度，避免把营销页的错位布局带入实时操作。
- 所有阵营至少使用颜色 + 图案/形状双编码，不能只靠红蓝区分。
- 字体、舰船轮廓、阵营纹章、声音与动效建立原创资产清单和来源记录。

### 性能预算

- 首屏关键内容不依赖 WebGL 初始化；战场模块按路由懒加载。
- 战斗目标为主流桌面设备稳定 60 FPS，低性能模式 30 FPS。
- 单次 frame 消息使用 delta 后目标小于 20 KB；客户端仅保留滑动窗口，完整回放按段加载。
- 动效不阻塞输入；倒计时基于服务端时间校准，不依赖 CSS 动画结束事件。

## 功能：运行、监控与恢复

### 涉及文件

- `infra/compose/docker-compose.yml`
- `infra/containers/*`
- `services/api/app/observability.py`
- `services/match-worker/app/observability.py`

### 可观测性

- 每个请求、比赛、回合和 Sandbox 调用携带 `trace_id`、`match_id`、`step`。
- 指标至少包含：排队时长、回合延迟、迟到率、Agent CPU/内存、Worker 崩溃、回放上传、结算重试和 WebSocket 重连。
- 日志不得记录 Agent Key、会话票据、完整用户代码或未脱敏 observation。
- 对规则 determinism 失败、排名重复结算和 Sandbox 逃逸信号设置高优先级告警。

### 数据一致性

- PostgreSQL 是业务状态真相源；Redis 丢失后可从数据库重建排队和比赛元数据。
- 运行中比赛使用 step checkpoint + command log；恢复必须验证 state hash。
- 回放上传成功后才把比赛从 `finalizing` 改为 `finished`。
- 排名结算与 finished 状态使用 outbox/幂等事务，避免“回放存在但没加分”或重复加分。

### 本地开发

- Docker Compose 启动 PostgreSQL、Redis、对象存储、API 和 Worker。
- Web 可独立热更新；Sandbox 使用与生产相同协议的本地容器实现。
- 提供固定 seed 的一键比赛、断线恢复、Agent 超时和 replay golden 测试。

## 技术验收标准

1. 固定 ruleset、seed、槽位和命令流在重复运行时产生相同结果和 state hash。
2. 提取后的引擎通过现有 Orbit Wars 单测和选定历史 replay 的逐步 golden 对比。
3. 人类与 Agent 接收同一步、同信息量的 Observation，并只能提交同一种 CommandBatch。
4. 迟到、重复、越权、超预算、NaN/Infinity 和错误 step 的命令均被确定性拒绝。
5. Agent 用户代码无法访问网络、宿主文件、平台凭据或其他比赛进程；超限时能被强制终止。
6. Agent 版本发布、模拟、挑战和排名结算在重试时保持幂等。
7. 运行中 Worker 崩溃后可从 checkpoint 恢复并得到相同 state hash；不能恢复时比赛不计分。
8. 完成的排位赛只产生一次 rating event；人类与 Agent 使用同一舰队 rating。
9. 公开回放不含 Agent Key、会话票据、私有源码或内部堆栈，并支持按 checkpoint 快速 seek。
10. 实时战斗在目标桌面设备达到 60 FPS，低性能模式达到 30 FPS，输入不被动效阻塞。
11. WebSocket 短暂断线可以续接；连续错过 10 回合按明确规则判负。
12. 关闭 WebGL 特效或启用 reduced motion 后，核心操作和回放信息仍完整可用。
13. 基础设施故障、用户/Agent 失败和正常败局在状态与计分上可以清楚区分。
14. Apache-2.0 引擎来源与原创/第三方资产来源均有可审计记录。

## 已接受风险与后续边界

- Python 沙箱是第一阶段成本最高的基础设施；先支持固定依赖镜像，不开放自定义依赖。
- 3 秒逐步窗口在 500 步极端局中可能达到约 25 分钟；上线前根据真实分布评估是否增加残局加速或更早的公开胜负规则，但不能静默改变现有 ruleset。
- 第一阶段只做单区域；比赛过程中跨区域高延迟通过匹配提示和延迟指标观察，不承诺全球低延迟。
- 4P、赛季和赛事不进入当前实现，但 ruleset、回放 participant 数组和排名服务避免写死只能有两个参与者。
