# 前置调研

## 调研问题

- 以 2026-07-18 的 AgenTank 公开网站为基准，Orbit/Wars 当前功能是否已经对齐？
- 哪些能力已经在后端真实实现，哪些只存在于演示界面或规划文档？
- 哪些 AgenTank 新能力值得补齐，哪些属于第二阶段以后或不应照搬？

## 结论摘要

**尚未全部对齐。** Orbit/Wars 的规则引擎、Agent 安全、版本、模拟、正式挑战、统一 rating、回放存储和可观测性底座已经覆盖 AgenTank 核心 Agent 竞技闭环的大部分后端能力，并额外提供真正的 Human 实时指挥和 Human/Agent 同协议同榜。

当前最大差距不在底层规则，而在“公开网站是否真的连上这些能力”：舰队创建、指挥中心、Agent Key、版本切换、竞技场和排行榜页面目前主要使用组件内状态或静态数据；回放播放器只获取了元数据，实际播放的仍是固定演示帧。因此当前形态更接近“后端完整 + 高保真交互样机”，还不是 AgenTank 那种登录后可持续使用的线上产品闭环。

此外，AgenTank 当前已扩展到团队、杯赛、社区内容、通知/邮件、成就、商店、邀请、钱包/链上资产、视频导出、多战斗分支和三语言。这些不应全部作为第一阶段对齐要求；应先补真实产品接线与双语，再决定社区和商业化模块。

## 已验证事实：AgenTank 当前公开能力

调研日期：2026-07-18。只核对公开页面、公开回放和 Agent Guide；未登录、未创建坦克、未提交表单，因此登录后能力以公开 UI/官方 Guide 为证据，不把未执行的写操作当成已实测结果。

### 核心创建与 Agent 闭环

- 首页主循环为创建坦克、交给 Agent、查看回放并迭代；同时宣传手写 JavaScript 编辑器作为直接参与方式。
- Tank Key 可让 Agent 读取上下文、发布代码、运行有限模拟、读取比赛/榜单、搜索公开对手并发起正式挑战。
- 发布要求记录 `submittedBy`，并支持 `main`、`raid`、`multiplayer` 三条代码分支。
- 模拟可直接携带未发布候选代码，也可使用最新已发布代码；响应包含逐帧原始回放。
- 正式挑战支持指定对手或随机对手、固定/随机地图、分段匹配范围与防刷分规则。

### 排名、对局和回放

- 公开对局历史有“精彩对局”筛选、结果原因、时间、Heat 指标和永久回放入口。
- 排行榜支持今日、本周、历史，以及胜率、胜场、精彩度、总分等排序；公开界面还出现个人/团队维度。
- 回放页包含双方版本、胜者、地图、结果、分享链接、重新播放、视频导出、人类回放链接和 Agent JSON 链接。
- Agent JSON 提供紧凑比赛总结、双方代码 hash、战术摘要、关键事件视图和深层回放链接，避免 Agent 必须先读取完整帧流。

### 社区、运营与扩展

- TankBook 支持 Agent 以坦克第一人称发布比赛评论、墙帖和回复，并有频率限制。
- 页面出现团队、杯赛创建、Raid、Battle Room、多分支代码、通知、每日战报、升段邮件、成就、商店、邀请奖励和创作者计划。
- 账号中心出现 GitHub、Google、邮箱、钱包登录/绑定；坦克可分享、铸造链上资产，并可导出为 Codex desktop pet。
- 设置支持英文、中文、日文以及战场视觉风格切换。
- 有独立更新日志、About、Q&A、隐私政策、服务条款、联系邮箱和 Discord 社区入口。

## Orbit/Wars 当前现状

### 已真实实现并可视为对齐或更强

| 能力 | 状态 | 事实 |
|---|---|---|
| 舰队领域与公开身份 | 对齐 | 有创建/读取/编辑 API、单账号约束和不可枚举公开 ID。 |
| Agent Key | 对齐 | scoped key、一次显示、摘要存储、轮换、撤销、限流与审计已实现。 |
| 不可变策略版本 | 对齐且更严格 | ZIP + manifest、hash 去重、验证状态、固定 runtime image、历史版本指针与比赛归因。 |
| Agent Sandbox | 更强 | 非 root、无网络、只读根、资源/日志/时间限制，并有真实 Docker 隔离测试。 |
| 模拟与正式挑战 | 基本对齐 | Agent/Owner 模拟、公开/内置对手、Agent 挑战、幂等与限流存在。 |
| 匹配与防刷分 | 对齐 | 同实力、低重复度、分差限制、重复对手计分倍率与审计原因。 |
| Rating 与榜单 API | 对齐 | Human/Agent 共用 fleet rating；今日/本周/历史和控制标签筛选不拆榜。 |
| 回放存储与分析 | 对齐且更强 | checksummed 流式回放、20 步 checkpoint、关键事件、指标与事实型胜因。 |
| 实时 Human 指挥 | Orbit/Wars 独有优势 | Human 与 Agent 使用同一 Observation/Command、时钟、匹配池和 rating；AgenTank 公开定位仍是不直接操控坦克。 |
| 确定性恢复与运维 | 更强 | checkpoint 恢复、state hash、幂等终局、trace、指标、告警、备份恢复和回滚演练。 |

### 关键未闭环项

| 优先级 | 差距 | 本地证据 | 影响 |
|---|---|---|---|
| P0 | 舰队创建页面未调用创建 API | `StartFlow.establish()` 只执行 `setStep(1)` | 用户看到成功，但数据库没有舰队。 |
| P0 | 指挥中心未连接真实版本和 Key | 版本数组写死；Key 由浏览器 `crypto.randomUUID()` 生成；撤销/切换只改 React state | 安全生命周期和版本管理只是演示。 |
| P0 | 竞技场未连接匹配/比赛/WebSocket | 排队只执行 `setQueued(true)`，之后固定跳转 `/battle/demo` | 无法从网站发起真实训练或排位。 |
| P0 | 排行榜页面使用静态舰队数组 | 页面内固定四支舰队，未消费公开榜单 API | 公开排名与真实 rating 脱节。 |
| P0 | 回放播放器仍播放演示帧 | 只 fetch `frameCount`；画面、事件、双方名称和 rating 变化均为固定常量 | 永久回放链接无法展示该比赛真实过程。 |
| P0 | 登录/会话入口缺失 | API 有 OIDC 校验，但 Web 无登录、回调、会话和账号中心页面 | 所有 Owner 操作无法形成真实线上闭环。 |
| P0 | 中英双语尚未实现 | 只有 `phase-2-bilingual/product.md`；现有页面大量硬编码中文/英文混排 | 不满足最新双语硬性要求，也落后 AgenTank 的中英日设置。 |
| P1 | 缺公开对局历史/发现页 | 只有单个 `/replay/[publicId]`，没有最新/精彩对局列表 | 用户无法从站内发现比赛与回放。 |
| P1 | Agent Guide 不完整 | 当前文档只覆盖发布和模拟，未完整说明挑战、榜单、对手、比赛历史、回放分析和错误恢复 | 外部 Agent 无法独立完成完整迭代循环。 |
| P1 | 缺 Agent 优化的紧凑回放视图 | 有 artifact/segment API，但无 compact summary/events/suggested-next-actions 投影 | Agent 分析需要读取更重的数据并自行理解。 |
| P1 | 模拟不支持未发布候选策略 | 当前模拟绑定不可变 ready 版本 | Agent 必须发布后才能测试，内循环成本高于 AgenTank。 |
| P1 | 缺真实模型归因展示与模型占比 | 后端保存 `source/submitted_by`，公开 UI 未真实消费 | Agent 生态身份和差异感较弱。 |
| P1 | 缺视频导出 | 回放只有网页和 gzip/segment | 分享门槛高于 AgenTank。 |
| P1 | 缺更新/Q&A/隐私/条款/About/联系页面 | 仓库有运维文档，但没有公开用户页面 | 上线可信度与自助支持不足。 |

### 有意不对齐或应后置

- 团队榜、团队管理、杯赛/锦标赛、Raid 和多人自由混战：Phase 1 原本明确后置，不能为了表面功能数量仓促加入。
- TankBook、Agent 墙帖和评论：有社区价值，但需要内容审核、反垃圾、隐私和人格边界，应独立产品设计。
- 商店、成就、邀请奖励、创作者计划：属于增长/经济系统，需在真实留存数据出现后再做。
- 钱包、链上铸造和 NFT：Orbit/Wars Phase 1 明确不包含链上资产，不建议为了竞品一致而增加。
- Codex pet、战场皮肤切换：有传播价值但非核心竞技闭环，优先级低于真实接线和双语。
- AgenTank 的技能、星星、墙/草/子弹机制属于其坦克玩法，不适合作为 Orbit Wars 的功能差距；Orbit/Wars 应继续深化轨道、生产、兵力和航迹特色。

## 功能对齐判断

| 维度 | 判断 |
|---|---|
| 规则/执行/安全底座 | 已对齐，部分能力更强。 |
| Agent 发布—模拟—挑战链 | 后端基本对齐；Guide 与未发布候选模拟仍有差距。 |
| 真实网站用户闭环 | 未对齐；关键页面仍是静态/本地状态演示。 |
| 排名与回放产品化 | 后端对齐，前端未真实消费；缺历史发现、Agent JSON 和视频导出。 |
| Human 直接参与 | Orbit/Wars 明显领先，是真正实时操作而不只是编辑代码。 |
| 国际化 | 未对齐；双语仅有需求文档，AgenTank 已有中英日设置和多语言更新页。 |
| 社区与运营 | 明显落后，但大部分不应进入首个补齐波次。 |
| 增长/商业化/链上 | 未对齐，且当前不建议对齐。 |

## 风险与约束

- 不能把“API 已存在”误报成“网站功能已可用”；后续验收必须从浏览器真实写入数据库并读回结果。
- 双语迁移与真实 API 接线会同时触及所有页面，应该共用一次路由和数据层改造，避免先接线后再整体返工。
- 当前回放播放器使用固定演示帧，若直接公开部署，会让用户误以为自己的比赛数据被篡改或丢失，属于上线阻塞项。
- 引入未发布候选策略模拟时，仍需沿用 Sandbox 验证与资源边界，不能绕过安全链路。
- AgenTank 的公开页面包含部分登录后组件和预加载文本；本报告只确认功能入口/官方说明，不声称所有写操作均已实测成功。
- 竞品功能快速变化；进入产品规划前应以本调研日期为基线，不把其页面结构、文案或视觉资产直接复制到 Orbit/Wars。

## 对产品讨论的启发

建议把下一波定义为“真实产品闭环 + 双语”，而不是扩张到团队或商店：

1. Web 登录与真实舰队创建。
2. 指挥中心连接真实 Agent Key、策略版本和最近战绩。
3. 竞技场连接匹配、比赛票据、WebSocket 与终局。
4. 榜单、档案和对局历史连接公开 API。
5. 回放播放器改为真实 checkpoint/segment 数据，增加 Agent compact/events JSON。
6. 中英文一次性覆盖上述真实流程，并加入缺 key/硬编码门禁。
7. 补全 Agent Guide、公开更新/Q&A/隐私/条款页面。

这七项完成后，Orbit/Wars 才能在核心 1v1 Agent 竞技产品层面与 AgenTank 对齐；Human 实时指挥、确定性恢复和事实型胜因会成为明确差异化，而不是追随功能。

## 来源与证据

### AgenTank（访问于 2026-07-18）

- https://agentank.ai/
- https://agentank.ai/agent-guide
- https://agentank.ai/leaderboard
- https://agentank.ai/history
- https://agentank.ai/history/mat_6RDf828vuMx4Wy62V
- https://agentank.ai/updates?lang=zh
- https://agentank.ai/qa

### Orbit/Wars 本地证据

- `apps/web/app/start/StartFlow.tsx`
- `apps/web/app/command/CommandCenter.tsx`
- `apps/web/app/arena/ArenaForm.tsx`
- `apps/web/app/leaderboard/page.tsx`
- `apps/web/components/battle/ReplayPlayer.tsx`
- `services/api/orbit_api/api/`
- `docs/agent-guide.md`
- `smooth/changes/agent-orbit-wars/phase-1/product.md`
- `smooth/changes/agent-orbit-wars/phase-2-bilingual/product.md`
