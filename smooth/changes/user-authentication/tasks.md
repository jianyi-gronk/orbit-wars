# 任务

## 阶段 1：认证基础与数据模型

- [x] **新增认证数据迁移** — 为密码凭据、邮箱 challenge、可撤销 session 和 OAuth identity 增加 PostgreSQL 模型、Alembic 迁移及约束测试。
- [x] **实现密码与 token 安全工具** — 实现版本化 scrypt 哈希、验证码摘要、opaque session token 摘要、输入规范化和常量时间比较，并覆盖边界测试。
- [x] **接入真实 Principal 会话** — 让现有 `current_principal` 支持数据库 session，同时保留受控 dev subject 与 OIDC 迁移兼容路径；验证既有所有权 API。

## 阶段 2：邮箱注册、登录与重置

- [x] **实现注册 challenge 与邮件发送** — 增加注册验证码申请、持久/短窗口限流、Resend 中英文邮件和非生产 debug 模式。
- [x] **实现邮箱注册与登录 API** — 原子创建用户/凭据/session，处理并发注册、密码失败计数、账户锁定与统一错误。
- [x] **实现密码重置与退出 API** — 完成 reset challenge、新密码更新、旧会话全撤销、当前会话退出和 Cookie 删除。
- [x] **补齐认证配置与会话投影** — 提供公开 auth config，完善 signed-out session 行为和稳定的双语错误 code。

## 阶段 3：Web 认证体验

- [x] **实现双语认证页面** — 实现中英 GitHub 单入口、首次授权自动注册说明、配置等待态、键盘与窄屏布局；邮箱表单由 feature flag 隐藏。
- [x] **将独立认证页收敛为全局登录弹窗** — 参考“韭见”的弹窗交互重构 GitHub 单入口，接入页头与受保护任务，保留旧链接兼容、返回路径、键盘焦点和移动端体验。
- [x] **接入全局账户入口** — 页头按会话显示单一登录入口或账户菜单，支持指挥中心、账户设置占位和退出。
- [x] **统一受保护任务返回** — 更新 StartFlow、任务决策与 401 处理，登录成功后安全返回创建舰队、实验室或竞技场原路径。

## 阶段 4：OAuth 与部署

- [x] **实现 GitHub 可配置 OAuth** — 增加 provider config、state/returnTo Cookie、回调、独立身份建档、重复登录复用和按配置显隐测试；Google 暂不开放。
- [x] **收紧预览与生产部署** — 增加 auth 环境变量、HTTPS 启动保护，并保证生产 bundle 默认不注入 dev subject；IP 预览脚本显式保留临时身份。

## 阶段 5：验证与交付

- [x] **执行认证安全与越权测试** — 覆盖 OAuth state、同源校验、重复身份复用、session 撤销、关闭的邮箱限流/锁定，以及既有跨账户舰队/策略/密钥访问回归。
- [ ] **执行中英浏览器验收** — 中英 GitHub 单入口、返回任务、移动端和控制台已通过；真实 GitHub 授权与登录后账户菜单等待 OAuth App + HTTPS 环境。
- [x] **记录部署前置与验证证据** — 更新环境文档、verify 证据和上线 runbook，按内聚批次 commit 后统一 push。
