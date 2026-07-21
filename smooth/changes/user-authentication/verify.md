# 验证

## 代码审查

- [x] GitHub 是页面唯一登录/注册入口；邮箱输入、密码输入和 Google 入口均不渲染。
- [x] GitHub 首次回调创建 `User` + `OAuthIdentity`，后续相同 provider subject 复用账户。
- [x] OAuth state 使用短时 HttpOnly Cookie，并以常量时间比较；`returnTo` 仅接受长度受限的站内绝对路径。
- [x] GitHub access token 只用于回调期读取资料，不写入数据库、Cookie 或日志。
- [x] 浏览器会话使用随机 opaque token，数据库只存 HMAC 摘要；退出和密码重置能撤销会话。
- [x] 认证写请求在存在 `Origin` 时校验同源；生产启用认证时强制 HTTPS。
- [x] Web 镜像默认不再编译 `NEXT_PUBLIC_ORBIT_DEV_SUBJECT`；IP 预览脚本必须显式注入临时身份。
- [x] 现有 dev subject 与旧 OIDC 验证保留为受控兼容路径，未改动舰队所有权主键。

## 自动化检查

- [x] Python Ruff：`ruff check services/api/orbit_api services/api/tests`
- [x] Python Mypy：认证模型、API、GitHub provider、Session 与安全工具 7 个模块无类型错误。
- [x] API 测试：`pytest services/api/tests -q`，全套通过，2 项既有环境型测试跳过。
- [x] Web TypeScript：`tsc --noEmit -p apps/web/tsconfig.json`
- [x] Web ESLint：`eslint .`
- [x] Web Vitest：13 个文件、68 项测试全部通过。
- [x] Next.js production build：编译、类型检查和 13 个静态页面生成通过。
- [x] Alembic：全新 SQLite 验证库从 `0001` 升级到 `0010` 成功。

## 浏览器证据

- [x] `/zh/auth?returnTo=/zh/start` 桌面布局正常；唯一 GitHub CTA 的返回路径为 `/zh/start`。
- [x] 中文页面中 `input[type=email]` 与 `input[type=password]` 均为 0，确认邮箱登录没有暴露。
- [x] `/en/auth` 显示英文 GitHub 单入口，邮箱/密码输入均为 0。
- [x] 约 390px 移动端断点无横向溢出，三项说明纵向排列，CTA 文案可见。
- [x] `/zh/start` 未登录状态跳转 `/zh/auth?returnTo=%2Fzh%2Fstart`。
- [x] 上述页面浏览器控制台无 error。

## 待外部环境验证

- [ ] 使用真实 GitHub OAuth App 完成授权、首次建档、重复登录、退出和账户菜单验收。
- [ ] 在正式域名 + HTTPS 下确认 `Secure` Cookie、正式 callback URL，并关闭 `ORBIT_DEV_AUTH` 与 Web dev subject。

当前 IP + 4000 预览继续使用临时指挥官身份，不开启 GitHub 登录。生产前置和环境变量见 `docs/authentication.md`。
