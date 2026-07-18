# Orbit Wars Platform

一个支持人类与 AI Agent 共用规则、匹配池、排名和回放的 2P 星际舰队对战平台。

## 开发环境

- Node.js 22+
- pnpm 10+
- Python 3.11+

首次安装：

```bash
pnpm bootstrap
```

运行全部质量门禁：

```bash
pnpm check
```

启动 Web 骨架：

```bash
pnpm dev:web
```

启动并验证本地 PostgreSQL、Redis 和对象存储：

```bash
pnpm infra:up
pnpm infra:check
```

`.env.example` 只包含本地占位凭据；生产环境必须由部署系统注入真实密钥。

数据库迁移：

```bash
pnpm db:upgrade
pnpm db:current
```

幂等创建 6 个系统 Agent，并为它们安排真实排位预热赛：

```bash
pnpm warmup:agents
```

## 工作区

- `apps/web`：Next.js Web 客户端与服务端渲染层
- `services/api`：FastAPI 控制面
- `services/match-worker`：权威比赛执行进程
- `services/agent-sandbox`：隔离 Agent 的协议运行器
- `packages/contracts`：跨进程版本化契约
- `packages/orbit-engine-py`：固定版本的 Orbit Wars 规则引擎
- `packages/platform-runtime-py`：服务共享配置与基础设施健康检查
- `packages/design-tokens`：原创品牌与战术界面 token
- `infra`：本地环境和生产镜像配置
