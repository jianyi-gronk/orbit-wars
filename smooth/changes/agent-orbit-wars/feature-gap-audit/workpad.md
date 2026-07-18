# 工作台

## 计划

- [x] 核对 AgenTank 首页、排行榜、对局历史、回放、Agent Guide、更新与 Q&A。
- [x] 盘点 Orbit/Wars API、Web 路由与真实数据接线状态。
- [x] 区分核心对齐、Orbit/Wars 差异化、上线阻塞项和应后置功能。
- [x] 将 P0/P1 差距转化为下一阶段产品需求与实施任务。
- [x] A01-A02：建立双语、数据层和真实会话边界。
- [x] A03-A05：接通舰队、指挥中心、竞技场、榜单和档案。
- [x] A06-A08：实现公开历史、真实回放、compact API 与候选模拟。
- [x] A09-A10：补文档/公开页并完成全量验证。
- [x] A11：修复首次用户不知道如何创建舰队和开始比赛的核心体验缺口。
- [x] A12：当前版本只开放 Agent 自主对战，Human 实时指挥保留实现但由功能开关封住。
- [x] A13：修复关闭 Human 入口后竞技场单卡拉伸、层级失衡和匹配原因长文本溢出的视觉回归。
- [x] A14：下载公开 Kaggle starter，记录来源/hash，接入创建 API 与双语模板选择，并验证初始 ready 版本和真实运行。
- [x] A15：幂等初始化 6 个系统 Agent，以平台/Kaggle 模板各 3 个加入统一匹配池，并安排真实排位预热赛与 rating 结算。
- [x] A16：保留唯一 rating，将总积分映射为青铜至大师段位，并在中英文榜单、档案和指挥中心显示段位与段内积分。
- [x] A17：修复已完成比赛未创建 ReplayArtifact 导致公开历史为空的问题，并回填当前数据库已有对局。
- [x] A18：修复 `/zh|en/replay/:id` 没有载入 replay.css 导致裸 HTML、战场铺满页面和事件文本堆叠的严重视觉回归。
- [x] A19：将 Kaggle 项目中 `notes/replays/YYYY-MM-DD/<episode>.json + index.csv` 的有效思路映射为线上架构的“日期分区不可变 artifact + ReplayArtifact 数据库索引”，并修复回放瞬时读取失败后只能看通用错误的问题。

## 验收标准

- 每项对比结论区分公开已验证事实、代码事实和推断。
- 不把静态演示页面认定为真实功能完成。
- 不把 AgenTank 的社区、商业化或链上模块无差别复制为第一阶段需求。
- 下一阶段优先补真实登录/数据闭环、真实回放和中英双语。

## 验证

- A01-A10：`smooth check`、`pnpm check`、Next build、SQLite release drill、PostgreSQL 0007 round trip 和生产 HTTP 双语 smoke 全部通过；详细证据见 `verify.md`。
- A11：参考 AgenTank 的三步开局信息节奏重做中英首屏和创建表单；浏览器实测“指挥中心立即开战 → 选择 Human → 获取本地训练对手 → 创建比赛 → 进入战术台 → 收到权威快照 → 提交回合指令”通过。
- A12：默认 `NEXT_PUBLIC_ENABLE_HUMAN_PLAY=false`；中英文指挥中心/竞技场只显示 Agent 出战，创建的训练赛双方均为 `controllerType=agent` 并正常完赛。Human 路由与实时控制实现未删除，显式开启功能开关后可恢复入口。
- A13：Agent 状态改为紧凑只读状态条，StartFlow 同步修正；对手卡不再渲染机器匹配原因串。中英文 DOM、桌面截图、Web lint/typecheck/test 和 Next 生产构建通过，窄屏断点增加整行主按钮与超窄屏重排。
- A14：Kaggle CLI 拉取 `pilkwang/orbit-wars-structured-baseline`，确定性提取源码并记录 notebook/source SHA-256；中英文创建页可选平台或 Kaggle 模板。测试账号创建后得到 `READY · kaggle` 版本，角度协议适配后真实训练赛 `match_jv06IfA7uB5mQN-zDT-rRQ8V` 正常完成。
- A15：`pnpm warmup:agents` 首次创建 6 个系统 Agent 和 6 场真实排位赛，第二次执行返回 `createdFleets=0`、`createdMatches=0`；全部比赛完成并产生 6 条 rating settlement。浏览器统一榜单显示 6 个 `WARM-*` Agent，每个 2 场记录。
- A16：后端边界验证包含 `625 → gold III / 25 points` 与大师阈值；中英文榜单分别显示“白银 I · 20.3 分”/“Silver I · 20.3 pts”，指挥中心同时显示段内积分、总积分与全服名次。390px 榜单隐藏冗余总积分列后 table 宽度由 378px 降至 316px。
- A17：要求每场 Worker 正常完成的比赛在标记 finished 前先上传不可变 gzip 回放并创建公开 ReplayArtifact；对历史 finished/no-replay 数据从 Redis Streams 权威 `match.frame` 回填，页面不得再以通用失败文案掩盖真实记录。
- A17 实测：11 场 finished 对局全部得到公开 ReplayArtifact 并关联 Match；同源历史接口返回 11 条记录，首场 replay segment 0 返回 20 条 `checkpoint + delta` 权威记录。新增 Worker 完整运行集成测试，确认新比赛在 finished 前自动上传并关联公开回放。
- A18：RootLayout 明确导入正式 `replay.css`，Replay HUD 收紧长 ID、双方舰队、评分变化、加载状态和战场高度；密集事件改为 marker，只在当前/悬停/键盘聚焦时显示标签。中英文和 620px 移动端均有独立响应式规则。
- A18 实测：本地正式回放路由已渲染完整 Replay 类名，实际 Next CSS chunk 包含 replay shell/stage/event track 规则；使用 102 帧、31 事件的真实预热回放核对 compact 数据。Web lint/typecheck、26 项测试与 Next 生产构建通过。
- A19：公开历史 API 新增 `replayArtifact: { schemaVersion, frameCount, sizeBytes, savedAt }`，历史卡片以 episode 索引视图显示地图、工件和保存时间。新 replay object key 按 `replays/YYYY/MM/DD/<match>/<checksum>.jsonl.gz` 分区，旧工件无需迁移。
- A19 实测：真实历史索引返回 `V1 · 102 帧 · 84463 bytes · savedAt`；同源 compact 与 0/20/40/60/80/100 六个 segment 全部 200。公开 GET 增加三次有界指数退避，History/Replay 两个错误态均可手动重试。Web 27 项测试、Python 165 项测试、全仓检查和 Next 生产构建通过。
- API 核心旅程覆盖创建、Key、发布、候选模拟、正式比赛、rating、榜单、档案、历史、compact 与永久回放。
- 生产 OIDC 身份提供商握手需要部署方凭据，已列为 staging 发布确认，不属于仓库内可执行检查。

## 备注

- 调研基线日期为 2026-07-18；AgenTank 功能会继续变化。
- Orbit/Wars 的 Human 实时指挥实现作为后续差异化能力保留，但当前公开产品入口默认关闭；确定性恢复和事实型胜因继续开放。
- 2026-07-18 实机复现：已有舰队时页头仍显示“创建舰队”；指挥中心没有开战主按钮；无对手时竞技场只显示通用错误且禁用开战按钮。
- A11 增加真实 Redis 队列消费进程；本地 API、Web、worker、PostgreSQL、Redis 和对象存储保持运行。
- 2026-07-18 实机复现：数据库有 14 场比赛（11 finished、3 failed）和 9 支舰队，但 ReplayArtifact 为 0；公开历史使用 replay inner join，因此返回空数组。根因是当前 `MatchWorker._finish` 只写结果和 rating，没有调用已有 ReplayStreamWriter/对象存储链路。
- 2026-07-18 回放视觉复现：`apps/web/app/replay/[publicId]/replay.css` 未被任何 layout/page 导入；旧无语言路由只 redirect，双语正式路由直接渲染 ReplayPlayer，导致组件只吃到 tactical 的绝对定位样式。即使补导入，旧事件轨道也会将大量标签绝对定位在 42px 高度内，需要一并收敛为 marker + hover/focus label。
- 2026-07-18 回放可用性复现：用户进入真实 replay 后看到 `REPLAY LINK / OFFLINE`；同时复查 compact 和 0/20/40/60/80/100 六个 segment 经同源代理均为 200，说明页面将一次瞬时 GET 失败永久锁在 error state，缺少有界重试和手动恢复。
- 2026-07-18 产品收敛：用户决定当前不支持手动玩，只留后续开放口子。

## 疑问

- 已决策：Agent compact replay JSON 和未发布候选策略模拟纳入本变更，但排在真实 Web 接线之后。
- 已决策：视频文件导出后置；本变更提供网页永久回放、原始 artifact 和 compact JSON。
