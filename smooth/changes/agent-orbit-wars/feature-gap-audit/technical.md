# 技术设计

## 总体方案

沿用 Next.js App Router + FastAPI + PostgreSQL/Redis/S3 的现有边界，不引入新的业务后端。Web 通过同源 `/orbit-api/*` 反向代理访问 FastAPI，OIDC access token 存放在 HttpOnly `orbit_session` cookie 中；FastAPI 继续作为权限与业务事实的唯一裁决者。

```text
Browser /zh|en/*
  ├─ /auth/*        -> Next OIDC PKCE handlers
  └─ /orbit-api/*   -> FastAPI /api/* (cookie/Authorization forwarded)
                         ├─ PostgreSQL domain state
                         ├─ Redis match queue/live bus
                         └─ S3 strategy/replay artifacts
```

## Web 架构

### 国际化

- `src/i18n.ts` 定义 `Locale = "zh" | "en"`、字典、路径辅助和格式化器。
- `proxy.ts` 对无语言页面按 `orbit_locale` cookie、`Accept-Language`、中文默认值跳转，并向渲染请求注入当前语言。
- 产品路由位于 `app/[locale]/...`；旧 URL 由 proxy 保留路径、查询和资源 ID 后跳转。
- 语言切换只替换首段语言并写偏好 cookie，不修改其余 URL。
- 公共系统文案通过字典或 locale 分支产生；用户内容不翻译。

### 身份与数据访问

- `/auth/login` 使用 Authorization Code + PKCE，state/verifier 使用短时 HttpOnly cookie。
- `/auth/callback` 交换 access token，写入 `orbit_session`；`/auth/logout` 清除会话。
- FastAPI 增加 `GET /api/v1/session` 和 `GET /api/v1/me/fleet`，前者返回最小会话信息，后者返回拥有舰队或 404。
- 本地验收允许显式 `ORBIT_DEV_AUTH=true` + `X-Orbit-Dev-Subject`，生产环境永不接受该头。
- `src/api.ts` 统一 API base、credentials、JSON 解析、稳定错误码和类型；写请求携带幂等键。

### 页面数据

- StartFlow 调用 fleet create，并把真实 `publicId` 交给下一步。
- StartFlow 通过 `strategyTemplate` 提交 `platform-basic` 或 `kaggle-structured-v11`；FastAPI 只接受白名单模板，并为舰队创建对应不可变 ready 版本。
- CommandCenter 并行读取 owned fleet、公开 profile、Agent keys；切换/生成/撤销后重新读取。
- `src/features.ts` 读取 `NEXT_PUBLIC_ENABLE_HUMAN_PLAY`；默认关闭时 StartFlow、CommandCenter 和 Arena 只暴露 Agent 控制，显式开启后恢复现有 Human 选择和战术台交接。
- Agent-only 状态不复用 Human/Agent 双选大卡，而以 `agent-lock` 紧凑状态条呈现；竞技场只显示本地化的 rating 差与近期交手摘要，不直接输出后端匹配原因串。
- Arena 先读取 offer，再创建 match；默认强制 `controllerType=agent`。保留的 Human 路径携带 ticket/match ID 进入战术台，供后续开关开放。
- Leaderboard、FleetProfile、History 使用真实 API，空态与错误态不回退到假数据。
- `competitiveRank` 由统一 `displayScore` 纯函数映射：每 100 分一个小段、每三个小段一个大段，1500 分进入大师；Web 只负责中英名称与“分/pts”本地化，不自行重算阈值。
- 回放先读取 metadata，再按 20-step checkpoint 拉取 segment，并由 `reconstructSegment` 生成权威帧；事件与分析来自 replay payload。
- 回放样式作为正式全局产品 surface 由 RootLayout 明确导入，不依赖旧 redirect 路由的目录位置；事件轨道只常显密度可控的 marker，完整名称在 hover/focus tooltip 与当前事件 callout 中展示，避免大量绝对定位文本互相覆盖。
- 历史保存沿用 Kaggle episode cache 的“轻量索引 + 每场完整工件”分层思路：PostgreSQL `ReplayArtifact` 作可查询索引，S3/MinIO 作 checksum 命名的不可变 `jsonl.gz` 工件；新工件 object key 按 UTC 日期分区，旧 key 保持可读。历史 API 返回 schema/frame/size/savedAt 投影，不让 Web 解压工件才能展示索引。
- 公开历史和回放 GET 请求允许有界重试；ReplayPlayer 的手动重试会清理旧错误/部分帧并重新从 compact 索引加载，AbortError 不参与重试。

## API 增量

- `GET /api/v1/session` → `{ authenticated, subject, displayName }`。
- `GET /api/v1/me/fleet` → owner fleet profile + current strategy ID；没有舰队返回 `fleet.not_found`。
- `GET /api/public/v1/matches` 返回已完成且公开可回放的比赛、双方归因、结果、rating 变化、时间和 replay ID。
- `GET /api/public/v1/replays/{id}/compact` 返回 metadata、result、participants、strategy attribution、analysis events、事实摘要与 artifact/segment 链接。
- Agent simulation payload 新增候选包；候选包必须复用发布验证和 Sandbox，使用临时存储并且不写 `strategy_versions`。
- `builtin_strategies/kaggle_structured_v11` 保存从公开 Kaggle notebook 确定性提取的源码、协议适配器与 provenance；导入脚本校验 kernel ID、公开状态和内容 hash，运行时继续使用无网络 stdlib Sandbox。
- Match worker 从每个参与者锁定的 `StrategyVersion.object_key` 解析白名单 builtin slug；Kaggle adapter 将 row observation 与有符号弧度转换为本站对象协议和 `0–2π` 角度，并执行六指令上限。
- `domain/warmup.py` 以稳定的保留 OIDC subject 幂等创建 6 个系统舰队，平台与 Kaggle starter 各占一半；显式 `warmup:agents` 初始化命令创建缺失 rating，并按稳定 fixture key 只安排一次真实 Agent 排位赛。
- Worker 完成排位赛后调用现有 `RatingService.apply_once` 做 exactly-once 结算；预热 Agent 不使用独立榜单、专用比赛表或页面静态数据。
- Worker 在正常终局时将初始帧、每步权威帧和双方命令写入 `ReplayStreamWriter`，终局 gzip 以 checksum 派生的不可变 key 上传对象存储；随后创建公开 `ReplayArtifact`、保存事实事件/指标并关联 `Match.replay_id`，完成后才进入 finished/rating 结算。
- 对升级前已经 finished 但缺少 replay 的本地比赛，回填命令从 Redis Streams 的 `match.frame` 权威事件重建 checkpoint/delta 工件；回填幂等跳过已有 replay 的比赛，不制造新比赛或 rating event。
- 榜单条目与公开舰队档案的 rating 投影新增 `competitiveRank: { tier, division, points }`；保留既有 `displayScore`、`tier`、`mu`、`sigma` 字段以兼容 Agent 客户端。

## 错误、安全与性能

- UI 只按稳定错误码本地化，保留原始 code；认证、权限、幂等和限流由 API 强制。
- Key 明文仅保存在当前 React 状态且一次显示；不写 localStorage、日志或分析事件。
- 公共列表限制最大页长；回放按 segment 渐进加载，不在首屏解压整个 artifact。
- 所有开发身份入口按服务端环境开关，生产配置默认关闭。

## 验证策略

- Python API 测试覆盖 session/me、公开历史、compact replay、候选模拟验证/不污染版本历史。
- Web Vitest 覆盖 locale/path、API 错误、回放重建和关键状态机。
- 全量运行 lint、typecheck、JS/Python tests、Next build。
- 使用真实数据库和 API 走通中英文 create→key→version→match→leaderboard→history→replay，并核对数据库持久化。
