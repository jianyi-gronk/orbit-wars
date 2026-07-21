# 技术设计

## 架构总览

```text
Browser
  ├─ SiteHeader LoginModal ─────────────┐
  ├─ protected action login event       │
  ├─ /zh/auth compatibility redirect    │
  └─ protected Orbit API requests       │
                                        ▼
Next.js /orbit-api rewrite ───────> FastAPI Auth API
                                        ├─ PostgreSQL users / credentials / challenges / sessions
                                        ├─ dormant email credential tables
                                        └─ GitHub OAuth
                                                  │
                                                  ▼
                                     opaque HttpOnly orbit_session cookie
                                                  │
                                                  ▼
                                    existing Principal + fleet ownership
```

认证事实源放在 FastAPI/PostgreSQL。Next.js 只提供双语界面、同源 API 转发和登录后导航，不保存密码、不签发会话，也不维护第二套用户库。

## 方案比较

| 方案 | 实现成本 | 长期维护 | 当前适配 | 主要代价 |
| --- | --- | --- | --- | --- |
| 托管 OIDC 身份服务 | 低 | 低 | 能复用现有 OIDC 骨架 | 需要外部租户、域名、供应商配置，登录 UI 受限 |
| 完整复制“韭见”认证 | 表面低、实际高 | 高 | 不适配 FastAPI/PostgreSQL | 形成 Next.js 与 API 两套身份事实源 |
| FastAPI 第一方认证 + 可配置 OAuth | 中 | 中高 | 与现有用户/舰队归属最一致 | 需要自行维护密码、邮件和会话安全 |

**当前方案：** FastAPI 管理 opaque session，以 GitHub OAuth 作为首发唯一身份入口；邮箱认证代码由 feature flag 关闭。

本次最重要的考量是让用户、舰队、策略和会话保持同一个 PostgreSQL 事实源，并避免从参考项目复制 SQLite/Next.js 专用实现。选择这一方案意味着承担密码与邮件认证的长期安全维护；后续仍可通过兼容的 `Principal` 抽象迁移到托管 OIDC。

## 功能列表

1. 认证数据模型与不可逆凭据
2. GitHub OAuth 自动注册与登录
3. 邮箱认证（默认关闭的后续能力）
4. 可撤销会话与现有 Principal 适配
5. 双语认证页面与全局账户入口
6. 预览/生产部署模式切换

## 共享基础

### 数据模型

在现有 `User` 基础上新增：

- `AuthCredential`
  - `user_id`：唯一外键
  - `email_normalized`：全局唯一
  - `password_hash`
  - `failed_attempts`、`locked_until`
  - `created_at`、`updated_at`
- `AuthChallenge`
  - `email_normalized`、`purpose`（`register` / `password_reset`）
  - `code_digest`、`expires_at`、`attempts`、`consumed_at`
  - `request_fingerprint`、`created_at`
- `AuthSession`
  - `user_id`、`token_digest`（全局唯一，不保存明文 token）
  - `expires_at`、`revoked_at`、`created_at`、`last_seen_at`
- `OAuthIdentity`
  - `user_id`、`provider`、`provider_subject`
  - `email`、`display_name`、`avatar_url`
  - `(provider, provider_subject)` 唯一

邮箱用户的稳定 `User.oidc_subject` 使用 `email:<sha256(normalized_email)>`；OAuth 用户使用 `github:<provider_id>` 或 `google:<sub>`。不改动现有舰队所有权查询，也不按相同邮箱自动合并。

### 会话格式

- Cookie 名继续使用 `orbit_session`。
- Cookie 值为 256-bit 随机 opaque token；数据库只保存 `HMAC-SHA256(AUTH_SECRET, token)`。
- Cookie 属性：`HttpOnly`、`SameSite=Lax`、`Path=/`，生产环境强制 `Secure`，有效期 30 天。
- `current_principal` 先保留明确受控的 dev subject 分支，再从 `AuthSession` 查找真实会话；Bearer OIDC 校验作为迁移兼容路径。
- 退出时撤销当前数据库会话并删除 Cookie，而不是只删除浏览器 Cookie。

### 通用安全工具

- 密码使用 Python `hashlib.scrypt`，随机 16-byte salt，版本化存储参数，比较使用 `hmac.compare_digest`。
- 验证码只保存 `HMAC-SHA256(AUTH_SECRET, purpose:email:code)`。
- 所有认证写操作校验同源 `Origin`，不开放宽泛 CORS。
- 关闭的邮箱认证按规范化邮箱和请求指纹在 PostgreSQL 执行持久窗口限流。
- 错误响应使用稳定 code，Web 按 locale 映射为中英文，不从服务端泄露账户是否存在。

## 后续能力：邮箱注册与密码登录（默认关闭）

### API

- `GET /api/auth/config`
  - 返回已启用渠道，不返回任何 secret。
- `POST /api/auth/register/request`
  - 输入：`email`
  - 输出：统一成功响应；开发模式可在显式测试开关下返回 debug code。
- `POST /api/auth/register/complete`
  - 输入：`email`、`password`、`code`、`locale`
  - 原子创建 `User`、`AuthCredential` 和 `AuthSession`，并消费 challenge。
- `POST /api/auth/login`
  - 输入：`email`、`password`
  - 验证失败统一返回 `auth.invalid_credentials`；成功重置失败计数并创建会话。

### 与现有代码的关系

- 注册成功后生成的 `Principal.subject` 能直接进入现有 `_account_for`、舰队创建和所有权查询。
- `/api/v1/session` 在无会话时继续返回 401；账户 UI 将 401 解释为 signed out。
- `apiFetch` 不再在真实部署构建中注入 `X-Orbit-Dev-Subject`。

### 设计决策

**为什么认证写在 API，而不是 Next.js Route Handler？**

舰队所有权和用户表已经属于 FastAPI/PostgreSQL。把凭据放在 Next.js 会形成两个数据库事务边界，注册成功但用户建档失败时难以恢复。

**为什么使用密码登录而不是每次邮箱验证码登录？**

产品要求明确参考“韭见”的注册验证码 + 日常密码登录；它减少日常邮件成本，同时保留邮箱所有权验证。

## 后续能力：找回密码（默认关闭）

### API

- `POST /api/auth/password/request`
  - 始终返回相同成功响应；存在账户时创建 reset challenge 并发邮件。
- `POST /api/auth/password/reset`
  - 输入：`email`、`code`、`newPassword`
  - 成功后更新密码、消费 challenge、撤销该用户所有旧会话，并签发新会话。

### 设计决策

重置密码后撤销所有旧会话，避免已泄露会话继续使用。注册与重置 challenge 用 `purpose` 隔离，验证码不能跨流程复用。

## 功能：GitHub OAuth

### API

- `GET /api/auth/github/start`
- `GET /api/auth/github/callback`

OAuth state 和 `returnTo` 使用短时 HttpOnly Cookie；回调后由 API 读取 GitHub user id，查找或创建独立 `User` + `OAuthIdentity`，再签发同一种 opaque session。GitHub OAuth App 当前流程不使用 OIDC nonce。

### 设计决策

- provider adapter 只请求基础身份 scope，不保存 access token 或 refresh token。
- provider 未配置时 `/api/auth/config` 声明渠道不可用，前端显示不可点击的配置等待态。
- 同邮箱不同 provider 不自动合并，避免邮件可信度差异导致接管。

## 功能：双语认证页面与账户入口

### Web 契约

- `LoginModal` 由全局页头账户入口托管，以 Portal 覆盖当前页面；页面只显示 GitHub 单入口，`returnTo` 只接受站内路径。
- 未登录任务通过 `orbit:open-login` 事件或 `?auth=login` 打开同一弹窗，避免每个业务组件维护一份弹窗状态。
- `/zh/auth`、`/en/auth` 只做兼容重定向：校验 `returnTo` 后回到目标页并附加 `auth=login`，不再渲染 `AuthPanel`。
- `AccountEntry` 请求公开的 `/api/auth/session`：
  - `authenticated=false`：显示“登录 / Sign in”。
  - `authenticated=true`：显示显示名和账户菜单。
- `StartFlow`、任务 CTA 和受保护动作统一请求全局登录弹窗并带上当前路径。

### 视觉与可访问性

- 保留页头三项主导航，不新增一级 Tab。
- 弹窗采用标准登录窗口层级，限制在约 384px 宽；不展示轨道示意图、功能卖点分栏、授权范围长文案或全屏说明。
- GitHub 单入口支持键盘、等待态、高对比和 reduced-motion。

## 功能：邮件与部署

- 邮件 provider 先支持 Resend，使用现有 `httpx`；邮件模板提供中英文主题和正文。
- 开发环境允许 `AUTH_EMAIL_DEBUG_CODE=1` 把验证码写入日志/测试响应；生产环境启动时禁止该配置。
- 新增 `ORBIT_AUTH_ENABLED`、`ORBIT_AUTH_SECRET`、`ORBIT_PUBLIC_BASE_URL` 与 GitHub OAuth 环境变量。
- 当 `ORBIT_AUTH_ENABLED=true` 且 `APP_ENV=production` 时，`ORBIT_PUBLIC_BASE_URL` 必须为 HTTPS，否则启动失败。
- 当前 IP 预览部署维持 `ORBIT_DEV_AUTH=true`，但 UI 明确为预览模式；正式域名部署关闭 dev auth 和公开 dev subject。

## 迁移与回滚

- Alembic 只新增认证表和索引，不删除 `users.oidc_subject`，现有预热舰队与回放不迁移。
- 认证功能由 `AUTH_ENABLED` 总开关控制；关闭后恢复当前预览身份路径，不删除已注册账户。
- 先上线数据库与隐藏 API，再上线 Web 入口，最后在 HTTPS 环境关闭 dev auth，避免切换期间所有用户失去访问。

## 技术验收标准

- 密码、验证码和 session token 明文均不进入数据库、日志或 API 响应（显式非生产 debug code 除外）。
- 注册完成、密码重置和 OAuth 首次登录使用数据库事务，不产生半创建身份。
- 同一邮箱并发注册最多成功一次，另一次返回稳定冲突错误。
- 过期、已消费、跨 purpose 和超次数验证码全部拒绝。
- 登录锁定、验证码频率和 IP 限流均可测试且不依赖单进程内存。
- 退出与密码重置后旧 session token 立即无效。
- 现有舰队、Agent Key、策略实验室和比赛 API 在真实 session 下通过所有权测试。
- Web 不再把 dev subject 编译进生产 bundle。
- 中英文认证页、返回原任务、窄屏与键盘流程通过浏览器验收。
