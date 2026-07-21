# Service Containers

- `Dockerfile.web` 构建 Next.js standalone 生产镜像。
- `Dockerfile.platform` 构建 API、Match Worker 与迁移共用的 Python 运行镜像。
- `services/agent-sandbox/Dockerfile` 构建隔离执行用户策略的 stdlib 沙箱镜像。

无域名预览部署由 `infra/deploy/ip-preview.sh` 编排；正式生产环境仍应使用不可变镜像、OIDC、TLS、备份与发布 runbook。
