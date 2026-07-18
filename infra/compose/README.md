# Local Compose

启动并等待全部服务健康：

```bash
pnpm infra:up
pnpm infra:check
```

停止服务但保留数据：

```bash
pnpm infra:down
```

清除本地 volume 和测试数据：

```bash
pnpm infra:reset
```

集成测试使用隔离端口：

```bash
pnpm infra:test:up
pnpm infra:test:check
pnpm infra:test:reset
```
