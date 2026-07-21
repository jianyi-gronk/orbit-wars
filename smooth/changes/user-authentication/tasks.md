# 任务

## 阶段 1：认证基础与数据模型

- [x] **新增认证数据迁移** — 为密码凭据、邮箱 challenge、可撤销 session 和 OAuth identity 增加 PostgreSQL 模型、Alembic 迁移及约束测试。
- [x] **实现密码与 token 安全工具** — 实现版本化 scrypt 哈希、验证码摘要、opaque session token 摘要、输入规范化和常量时间比较，并覆盖边界测试。
- [x] **接入真实 Principal 会话** — 让现有 `current_principal` 支持数据库 session，同时保留受控 dev subject 与 OIDC 迁移兼容路径；验证既有所有权 API。

## 阶段 2：邮箱注册、登录与重置

- [ ] **实现注册 challenge 与邮件发送** — 增加注册验证码申请、持久/短窗口限流、Resend 中英文邮件和非生产 debug 模式。
- [ ] **实现邮箱注册与登录 API** — 原子创建用户/凭据/session，处理并发注册、密码失败计数、账户锁定与统一错误。
- [ ] **实现密码重置与退出 API** — 完成 reset challenge、新密码更新、旧会话全撤销、当前会话退出和 Cookie 删除。
- [ ] **补齐认证配置与会话投影** — 提供公开 auth config，完善 signed-out session 行为和稳定的双语错误 code。

## 阶段 3：Web 认证体验

- [ ] **实现双语认证页面** — 增加登录、注册、验证码、找回密码状态机，处理 busy/error/success、键盘、窄屏和 reduced-motion。
- [ ] **接入全局账户入口** — 页头按会话显示单一登录入口或账户菜单，支持指挥中心、账户设置占位和退出。
- [ ] **统一受保护任务返回** — 更新 StartFlow、任务决策与 401 处理，登录成功后安全返回创建舰队、实验室或竞技场原路径。

## 阶段 4：OAuth 与部署

- [ ] **实现 GitHub/Google 可配置 OAuth** — 增加 provider config、state/PKCE/nonce、回调、独立身份建档和按配置显隐测试。
- [ ] **收紧预览与生产部署** — 增加 auth 环境变量、HTTPS 启动保护，并保证生产 bundle 不注入 dev subject。

## 阶段 5：验证与交付

- [ ] **执行认证安全与越权测试** — 覆盖验证码、限流、锁定、并发、session 撤销、CSRF、跨账户舰队/策略/密钥访问。
- [ ] **执行中英浏览器验收** — 走通注册、登录、重置、退出、返回任务、移动端和账户菜单，无控制台错误。
- [ ] **记录部署前置与验证证据** — 更新环境文档、verify 证据和上线 runbook，按内聚批次 commit 后统一 push。
