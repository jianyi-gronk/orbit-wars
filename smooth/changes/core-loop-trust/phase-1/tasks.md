# 任务

## 阶段 1：数据与共享规则

- [x] **持久化草稿关联 simulation** — 新增 0009 迁移与 `StrategyDraft` 关联字段，草稿变更时清除旧资格。
- [x] **建立 candidate classification 与发布资格规则** — 用现有 participant candidate attribution 判断私人策略模拟，并实现服务端资格计算。

## 阶段 2：API 可信边界

- [x] **修复公共历史与 replay 隐私** — 公共 matches、fleet profile、replay API 过滤 candidate simulation，worker 默认写入私有 replay。
- [x] **收紧 Strategy Lab 模拟与发布 API** — workspace 持久返回关联状态，publish 仅接受当前草稿已完成且验证通过的 simulation。
- [x] **扩展比赛状态 API** — 返回 result、时间、参与者名称和 replay readiness，保持参赛者鉴权。

## 阶段 3：Web 核心链路

- [x] **修复历史 mode 展示** — 按响应的 training/ranked/unknown 双语显示，不再硬编码排位赛。
- [x] **实现 Strategy Lab 状态恢复与发布锁** — 自动刷新进行中 simulation，显示锁定原因，终态后停止轮询。
- [x] **实现比赛专属状态页** — Arena 创建后进入具体 match，自动追踪到 replay，失败时可重试或返回。
- [x] **展示 replay 来源上下文** — 有效来源显示战果、高光、mode 与返回入口；无效来源不泄露。
- [x] **修复 start 与退出登录语义** — 双语标题、已有舰队状态 CTA、未登录隐藏退出项。

## 阶段 4：验证

- [x] **补充 API 聚焦测试** — 覆盖隐私、mode、发布门禁、状态恢复、match replay readiness 和 replay 权限。
- [x] **补充 Web 聚焦测试** — 覆盖 mode 文案、状态页路径、发布锁、来源上下文和账户菜单。
- [x] **运行迁移与聚焦检查** — 执行相关 API/Web 测试、格式、lint、typecheck，并记录结果。
- [x] **执行生产态浏览器验收** — 完成训练赛、状态页、回放、策略模拟、发布门禁、历史隐私和中英文检查。
- [x] **修复首页滚轮死区** — 将监听从内容容器提升到首页窗口，验证页头、内容区、连续下滑和反向滚动。
