# 技术设计

## 架构总览

```text
StrategyLab 页面
  ├─ GET/PUT 私有草稿 ───────────────> StrategyDraft（每舰队一份）
  ├─ POST candidate simulation ──────> 源码打包 → 既有 Sandbox 校验 → Match/Replay
  ├─ POST publish ───────────────────> 源码打包 → StrategyVersion → 校验 → current
  └─ POST AI assist ─────────────────> AI quota ledger → DeepSeek V4 Flash
                                             └─ explanation + proposed source + diff

SessionAction ──> fleet + current ready version ──> arena
                       └─ Agent Key 只影响外部自动化入口
```

## 功能列表

1. 移除 Agent Key 对开战任务的门禁。
2. 私有策略草稿与可编辑平台模板。
3. Owner 身份的候选模拟、发布和版本切换。
4. DeepSeek AI 辅助与免费额度账本。
5. 中英文策略实验室、入口和回放回流。

## 共享基础

### 源码包

新增 `domain/strategy_source.py`，只接受单文件 Python 源码并生成确定性 ZIP：

- `manifest.json` 固定为 schema v1、`main.py:agent` 和 stdlib runtime。
- `main.py` 最多 128 KiB，必须为 UTF-8，禁止额外文件和用户自定义 runtime。
- ZIP 固定时间、排序与权限，确保同一源码产生同一 content hash。
- 平台基础模板从现有 `basic.py` 读取；Kaggle 模板在许可证确认前只显示来源，不提供站内可编辑副本。

### 错误与响应

- API 返回稳定 code，不把 Sandbox 路径、供应商响应体或异常堆栈发送到浏览器。
- 草稿更新使用 `revision` 乐观锁；冲突返回 409，防止多个标签页静默覆盖。
- 所有写接口沿用 OIDC owner 身份和现有 `get_owned_fleet()` 边界，不需要 Agent Key。

## 功能：任务门禁调整

### 涉及文件

- `apps/web/src/mission.ts`
- `apps/web/components/product/SessionAction.tsx`
- `apps/web/src/mission.test.ts`

### 设计

`resolveMissionAction()` 只按 session、fleet 和 current strategy readiness 决定主任务：

- 无舰队 → 创建舰队。
- 无 ready current strategy → 优化策略。
- 有 ready current strategy → 立即开战。

Agent Key 不再进入主任务状态机；指挥中心继续显示外部 Agent 接入状态。

## 功能：私有策略草稿

### 数据模型

`StrategyDraft`：

- `fleet_id` 唯一外键。
- `base_strategy_version_id` 可空。
- `source_code`、`mode`（guided/code）、`parameters` JSON。
- `revision`、`last_validation` JSON、`validated_content_hash` 可空。
- `created_at`、`updated_at`。

首次 GET 若没有草稿，基于平台基础模板创建；当前版本是平台基础 builtin 时记录为 base。自定义不可逆源码只以 code 模式打开，guided 模式只能编辑平台生成的结构化源码。

### API

- `GET /api/v1/fleets/{fleet_id}/strategy-lab`
- `PUT /api/v1/fleets/{fleet_id}/strategy-lab/draft`
- `POST /api/v1/fleets/{fleet_id}/strategy-lab/reset`

响应同时返回草稿、当前版本、版本列表、可编辑模板、AI 额度和最近模拟摘要，减少页面首屏请求竞争。

## 功能：候选模拟与发布

### API

- `POST /api/v1/fleets/{fleet_id}/strategy-lab/simulations`
  - 输入 `revision`、`opponentId`、`idempotencyKey`。
  - 从服务器草稿生成 package，走现有 `validate_candidate_package()` 与 `create_simulation(candidate=...)`。
  - 成功后把 validation 与 content hash 写回同 revision 草稿。
- `POST /api/v1/fleets/{fleet_id}/strategy-lab/publish`
  - 只允许当前草稿 hash 与最近通过验证的 hash 一致。
  - 调用既有 publication 与 validation，再按明确 `makeCurrent` 设置 current。
- 既有 current strategy PATCH 保留，用于恢复历史 ready 版本。

模拟不写 StrategyVersion，不改变 current/rating；发布复用不可变对象存储和去重语义。

## 功能：AI 副驾与额度

### 数据模型

`AiCreditAccount` 每用户一行：`remaining`、`granted`、`updated_at`。

`AiAssistRequest` 记录 `public_id`、用户、草稿 revision、kind、cost、status、model、输入/输出 token、错误 code 和时间。源码、完整 prompt、模型原始响应不落账本。

### API

- `POST /api/v1/fleets/{fleet_id}/strategy-lab/ai-assists`
  - 输入 `kind`（explain/suggest/patch）、`deep`、`consent`、可选用户目标。
  - 普通 cost=1，deep cost=2。
  - 每日最多 5 credits、单用户并发 1、全站每日预算由环境变量控制。
  - 供应商成功并解析出合法结构后才原子扣减；失败标记 request 但余额不变。

DeepSeek 客户端使用可注入接口，生产实现通过 OpenAI-compatible HTTPS 调用 `deepseek-v4-flash`。配置缺失时返回 `ai.unavailable`；页面仍完整显示手动功能。

发送内容只包含规则摘要、草稿源码、用户目标和用户明确选中的公开回放摘要。`user_id` 使用服务端 secret 对内部 user UUID 做 HMAC，不发送 OIDC subject、邮箱、Fleet 名、Key 或 Cookie。

Patch 响应要求 JSON：`summary`、`reasoning`、`proposedSource`、`tests`。服务端验证源码大小并计算 unified diff；浏览器只能在用户点击接受后把 proposed source 写入草稿。

### 额度一致性决策

| 方案 | 优点 | 风险 |
|---|---|---|
| 调用前扣减、失败返还 | 并发控制简单 | 返还路径容易遗漏 |
| 调用成功后扣减（采用） | 符合“失败不扣” | 需要 reservation 防并发 |

采用 request reservation + 用户级并发锁；成功时在同一事务校验余额并扣减，失败只释放 reservation。全站预算熔断在发起供应商请求前检查。

## 功能：Web 策略实验室

### 路由与组件

- 新增双语 `/[locale]/strategy-lab` 路由，保持现有 catch-all 页面结构。
- `StrategyLab` 客户端组件包含 Overview、Guided、Code、AI、Simulation、Versions 六个区域，但不增加一级导航 tab；使用页面内分段和 sticky action rail。
- Code 首发使用受控 textarea + 行号/错误摘要，不引入重型浏览器 IDE；后续可替换编辑器而不改变 API。

Guided 只暴露 launch ratio、minimum ships 与 target preference。切换到 Code 后保留源码；自定义源码不能无损回到 Guided 时显示明确“重置为平台模板”动作。

入口接到创建完成页、指挥中心、任务菜单、回放结果和 Arena。页面卸载时未保存草稿给出浏览器提示。

## 测试与技术验收

- 迁移可 upgrade/downgrade；旧舰队按需生成草稿和 30 credits。
- Owner 隔离、revision 冲突、源码上限、确定性打包和 hash 测试。
- 候选模拟不创建版本、不改变 current/rating；未验证或 stale 草稿不能发布。
- AI 缺 key、拒绝、超时、格式错误、日限额、并发、预算、成功扣减和失败不扣均有测试。
- prompt/日志/响应不包含 Agent Key、OIDC subject 或环境变量。
- 中英文页面支持无 DeepSeek 配置、额度耗尽、模拟失败和窄屏。

