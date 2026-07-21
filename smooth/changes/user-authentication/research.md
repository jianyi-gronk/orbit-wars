# 前置调研

## 调研问题

- Orbit Wars 当前是否已经具备真实用户登录与注册能力。
- “韭见”的认证实现中，哪些产品机制和安全规则值得复用。
- 当前无域名、HTTP IP 预览部署对真实认证有什么限制。

## 已验证事实

- Orbit Wars Web 已有 OIDC 登录、回调和退出路由，并使用 PKCE、state、HttpOnly Cookie 与安全的 `returnTo` 白名单逻辑。
- Orbit Wars API 已有 OIDC JWT 校验器、Cookie/Bearer Token 读取和 `users.oidc_subject` 唯一身份字段，但应用启动代码没有初始化并挂载 OIDC 校验器。
- 当前预览部署显式开启 `ORBIT_DEV_AUTH=true`，Web 构建固定注入 `preview-commander`，所以所有访问者共享同一个预览身份；这不是注册或登录系统。
- 当前页头没有账户入口；未登录用户只有进入 `/start` 后才会看到“登录并开始”，而该按钮当前只会跳转到尚未配置的 OIDC 提供方。
- “韭见”支持邮箱密码注册、六位邮箱验证码、邮箱密码登录、GitHub OAuth、Google OAuth、登录后返回、退出和账户菜单。
- “韭见”对注册验证码设置 10 分钟有效期、60 秒发送间隔、15 分钟窗口最多 5 次、最多 5 次校验；密码登录连续失败 5 次后锁定 15 分钟，并使用带随机盐的 scrypt 密码哈希。
- “韭见”使用 SQLite、Next.js Route Handler 和自签名 Cookie；Orbit Wars 使用 PostgreSQL、FastAPI 业务 API 和 Next.js Web，因此其代码不能直接复制。
- 当前公开地址是 `http://47.98.155.60:4000`。在明文 HTTP 上提交密码或长期会话不满足公开用户认证的安全前提。

## 当前现状

```text
访问网站
  └─ Web 自动注入 preview-commander
       └─ API 接受 X-Orbit-Dev-Subject
            └─ 所有人看到并操作同一个账户
```

现有 OIDC 骨架更接近“接入外部身份服务”的半成品，不提供站内注册页、邮箱验证码、密码凭据、找回密码、账户菜单或真实多用户隔离。

## 风险与约束

- 真实认证上线前必须先有域名和 HTTPS；当前 IP + HTTP 只能继续用于无密码的预览模式。
- Email、GitHub、Google 身份不能仅凭相同邮箱自动合并，否则存在账户接管风险；账户绑定应使用已登录状态下的显式确认流程。
- 当前数据模型一个用户只能拥有一支舰队。认证上线后该约束会直接成为产品规则。
- 预热 Agent 和 `preview-commander` 的历史数据不能自动归属给第一个真实注册用户。
- 注册、登录、验证码和找回密码接口需要限流、枚举防护、审计与双语错误文案。
- 站内自建密码认证会增加长期安全维护责任；若改用托管身份服务，可减少密码存储责任，但会增加供应商依赖和外部配置。

## 对产品讨论的启发

- 第一阶段应交付完整账户闭环，而不是只把现有 OIDC 按钮露出来。
- 可参考“韭见”的单面板登录/注册交互、返回原任务、验证码和失败锁定规则，但应按 Orbit Wars 的星际游戏视觉和中英双语重做。
- 登录入口应融入克制的全局页头：未登录显示单一“登录”，已登录显示账户标识；不能重新引入多个竞争 CTA。
- 受保护动作应统一触发登录并保存原任务，认证成功后继续创建舰队、策略实验室或开战流程。
- 建议把邮箱注册与登录作为基础能力，GitHub 和 Google 作为按配置显示的快捷入口；身份合并留到后续账户设置阶段。

## 来源与证据

- `apps/web/src/auth.ts`
- `apps/web/app/auth/login/route.ts`
- `apps/web/app/auth/callback/route.ts`
- `apps/web/components/product/SiteHeader.tsx`
- `apps/web/app/start/StartFlow.tsx`
- `services/api/orbit_api/security/oidc.py`
- `services/api/orbit_api/main.py`
- `services/api/orbit_api/db/models.py`
- `infra/deploy/ip-preview.sh`
- `/Users/jianyi-gronk/Desktop/product/韭见/components/auth/LoginPanel.tsx`
- `/Users/jianyi-gronk/Desktop/product/韭见/lib/auth/email-login.ts`
- `/Users/jianyi-gronk/Desktop/product/韭见/lib/auth/session.ts`
- `/Users/jianyi-gronk/Desktop/product/韭见/tests/email-login-cleanup.test.ts`

