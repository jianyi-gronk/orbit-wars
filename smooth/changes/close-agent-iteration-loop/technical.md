# 技术设计

## 架构总览

```text
公开比赛 API ──> HomeBattleFeed ──> 首个 segment ──> BattleStage
                     └──────────────> 最近三场回放卡片

SessionAction ──> session ──> owned fleet ──> profile + Agent keys
                     └──────────────> resolveMissionAction()

ReplayPlayer ──> compact replay ──> buildAgentAnalysisBrief()
                                      └── clipboard（公开数据）
```

本轮不新增后端接口。公开比赛、compact replay、segment、舰队档案与 Agent Key 列表均已有稳定接口。

## 共享类型与纯函数

新增 `apps/web/src/mission.ts`：

- `MissionState` 表示五种用户状态。
- `resolveMissionAction()` 根据 session、fleet、profile 和 keys 生成目标路径与中英文标签。
- 纯函数单元测试覆盖全部状态，React 组件只负责请求和展示。

新增 `apps/web/src/public-replay.ts`：

- 统一首页、历史和回放使用的公开比赛与 compact replay 类型。
- `agentReplayDataUrl()` 根据当前 origin 与配置 API base 生成绝对公开数据 URL。
- `buildAgentAnalysisBrief()` 生成无密钥的结构化交接文本。

`apps/web/src/api.ts` 导出安全的 `apiUrl(path)`，供展示公开 API 链接；它不附加 Cookie、dev subject 或密钥。

## 功能：状态感知下一任务

`SessionAction` 依次读取：

1. `/api/v1/session`
2. `/api/v1/me/fleet`
3. 并行读取公开 fleet profile 与私有 Agent Key 列表

判断规则：

- 无有效 Key：`connect-agent`。
- 无 `currentStrategyVersionId`，或该版本不为 `ready`：`deploy-strategy`。
- 其余为 `battle-ready`。

任何非 404 的后续请求异常不应错误地把用户当成未登录；组件退回指挥中心并显示通用“继续任务”。页头只保留一个主按钮，退出移动到 `SiteHeader` 的任务菜单。

## 功能：首页真实回放预览

新增 `HomeBattleFeed` 客户端组件：

- 请求 `/api/public/v1/matches?period=all&limit=3`。
- 若首场有 replay ID，请求 compact 和 `/segments/0`，用 `reconstructSegment()` 得到最多首段 20 帧。
- 使用现有 `BattleStage` 绘制真实帧；预览不加载其余分段。
- 自动播放采用低频定时器，只在组件可见、非 reduced-motion 且帧数大于 1 时运行。
- compact、segment 或比赛列表任一失败都进入可读占位，不影响首页其他部分。

首屏用 `HomeBattleFeed` 的 preview 变体替换 `orbital-radar`；第三幕用 feed 变体替换静态 `network-map`。两个实例共享模块级缓存 Promise，避免同页重复请求比赛列表和首段。

## 功能：Agent 回放分析交接

`ReplayPlayer` 在 compact 数据可用后生成：

- 当前人类回放绝对 URL。
- compact replay 绝对公开 URL。
- 双方舰队、模式、地图、结果、评分变化。
- facts 与关键事件摘要。
- 明确要求 Agent 分析决策转折、失败原因和下一版可验证改动的提示词。

复制操作统一通过一个本地 helper，更新 `copyState` 并在 2 秒后复位。Clipboard API 不可用或拒绝时显示错误，不静默吞掉。

## 样式与响应式

- 首页真实战场保持 1:1 画布，嵌入首屏右侧的 HUD 框；窄屏缩小为背景式战场卡，但链接和对局摘要仍可点击。
- 最近对局卡采用三列桌面/单列移动布局，不增加首页高度场景数量。
- 回放交接区放在事实结果下方，与原始工件链接区分层级；主按钮使用金色，两个复制链接使用次级边框。
- 所有 hover 状态显式保持文字颜色，避免此前按钮悬浮文字消失问题。

## 测试与验证

- `mission.test.ts`：五种状态、错误回退和双语标签。
- `public-replay.test.ts`：绝对 URL、交接包字段、密钥字符串不出现。
- `quality.test.ts`：首页只取 segment 0、reduced-motion 保护、回放复制动作和按钮 hover 对比度。
- 工程验证：web test、lint、typecheck、build。
- 浏览器验证：`/zh`、`/en` 首页桌面/窄屏、真实帧与最近对局、五态中当前可复现状态、回放复制反馈和控制台。

## 技术验收标准

- 首页两个 feed 实例最多触发一次比赛列表、一次 compact 和一次 segment 0 请求。
- 首页不读取 segment 20 及以后，不增加完整回放下载成本。
- SessionAction 卸载时中止请求，加载态不造成布局剧烈跳变。
- 交接包完全由公开 compact 数据构成，代码中不读取或拼接 Agent Key。
- 新组件有无数据、失败、reduced-motion 和窄屏路径。
