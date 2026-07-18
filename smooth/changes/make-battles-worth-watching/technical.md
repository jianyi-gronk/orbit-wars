# 技术设计

## 架构总览

```text
Match + RatingEvent + ReplayAnalysis
              │
              ├── competition analytics ──> leaderboard sort / record
              │                         └──> intensity / highlights / featured
              │
              └── public competition API ──> LeaderboardView / HistoryView

Fleet + Profile + Agent Keys + one-time secret
              └── CommandCenter ──> command mission resolver
                                └──> Agent handoff bundle ──> clipboard
```

## 功能列表

1. 共享竞技统计与战况强度
2. 周期榜单排序
3. 观众化历史与高光
4. Command Center 动态任务与 Agent 交接
5. 自动化和浏览器验证

## 共享基础：竞技统计

### 涉及文件

- 新增 `services/api/orbit_api/domain/competition.py`
- 修改 `services/api/orbit_api/api/leaderboard.py`
- 修改 `services/api/tests/test_leaderboard.py`

### 接口

```python
class CompetitionRecord(TypedDict):
    matches: int
    wins: int
    losses: int
    draws: int
    winRate: float
    adjustedWinRate: float

class BattleIntensity(TypedDict):
    score: int
    band: Literal["routine", "contested", "volatile"]
    signals: list[str]

def competition_record(rows, slot) -> CompetitionRecord: ...
def battle_intensity(analysis, frame_count, rating_changes) -> BattleIntensity: ...
def select_highlights(events, limit=3) -> list[dict]: ...
```

样本保护采用 Beta(1,1) 平滑：`adjustedWinRate = (wins + 1) / (matches + 2)`。UI 显示原始胜率，排序使用 adjustedWinRate；这样无需隐藏低场次舰队，同时避免 1/1 直接压过稳定战绩。

战况强度只读取权威字段：帧数、星球易手、兵力/产能领先变化、母星失守、淘汰和最大 rating delta。分数裁剪到 0～100，signals 返回参与计分的可解释英文代码。`featured` 阈值固定为 60。

## 功能：周期榜单排序

### API

`GET /api/public/v1/leaderboard` 新增：

```text
sort=score | win_rate | wins
```

- 未传 sort：`all → score`，`today/week → win_rate`。
- `score`：displayScore、周期胜场、名称稳定排序。
- `win_rate`：adjustedWinRate、胜场、场次、displayScore。
- `wins`：胜场、adjustedWinRate、displayScore。

响应增加顶层 `sort`，record 增加 draws、winRate、adjustedWinRate。rank 在排序完成后重新编号。

### Web

路由读取并验证 sort，`LeaderboardView` 把 period/control/sort 一起写入 URL。表格展示完整周期战绩与原始胜率；说明文字解释样本保护只用于排序。

## 功能：观众化历史与高光

### API

`_public_match()` 增加：

```json
{
  "intensity": { "score": 72, "band": "volatile", "signals": ["lead_changes", "rating_swing"] },
  "highlights": [{ "type": "home_planet_lost", "step": 84, "slot": 0 }],
  "featured": true
}
```

highlights 按事件语义优先级选择，并尽量避免三个事件集中在同一步。前端将 step 写入 replay URL 查询参数；ReplayPlayer 读取 `?step=` 后在帧加载时定位。

### Web

- `PublicMatchSummary` 增加 intensity/highlights 类型。
- 提取共享 `replayEventName()`，历史和回放使用同一双语事件名。
- 卡片采用结果带 + 双方对阵 + 强度/原因/时间 + 高光 + 回放按钮。
- 回放工件信息放进 `<details>`，仍可验证但不抢主层级。

## 功能：Command Center 动态任务与 Agent 交接

### 共享工具

- 新增 `apps/web/src/clipboard.ts`，抽出 ReplayPlayer 已验证的 Clipboard API 超时与 legacy fallback。
- 新增 `apps/web/src/agent-handoff.ts`：纯函数生成中英文交接包并测试不遗漏 Key、Guide、API Base、fleet ID。

### 状态模型

```ts
type CommandMission =
  | "needs-agent-key"
  | "copy-handoff"
  | "needs-ready-strategy"
  | "battle-ready";
```

优先级为：存在当前一次性 secret → copy-handoff；无 active key → needs-agent-key；无当前 ready 版本 → needs-ready-strategy；否则 battle-ready。

复制包只在 `secret !== null` 时生成。组件不把 bundle 写入 state、storage 或 API；点击时即时构造并写剪贴板。ReplayPlayer 同时改用共享 clipboard helper，避免两套兼容逻辑。

## 技术验收标准

- 竞技统计函数为纯函数，平局、零场次、低样本、同分排序和缺失 analysis 均有测试。
- intensity 不读取生成文本或私有字段；featured 只由 intensity 阈值决定。
- leaderboard sort 参数非法时返回 422；默认排序与 period 对应。
- replay `?step=` 不超过 frame 范围，分段渐进加载时最终能定位到目标帧。
- Agent handoff 不进入日志、localStorage、sessionStorage、公共 API 或 React 持久 state。
- Clipboard 兼容路径由 Replay 与 Command 共用。
- API test、web test、lint、typecheck、build 通过。
