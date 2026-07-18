# 工作台

## 计划

- [x] 配置回放星球标签显示模式
- [x] 将兵力数字居中到星球内部
- [ ] 自动化与浏览器回归（自动化已通过，浏览器视觉确认待手动刷新）

## 边界

- 星球 ID 只是不展示，仍保留在底层回放与帧数据中。
- 本次不修改 replay schema、压缩工件或历史数据。
- LiveBattle 维持默认兼容行为。

## 验证

- 单元测试验证标签格式。
- Web 类型、测试与构建检查。
- 指定旧回放的实际画面与浏览器错误检查。

## 结果

- `pnpm --filter @orbit-wars/web typecheck`：通过。
- `pnpm --filter @orbit-wars/web lint`：通过。
- `pnpm --filter @orbit-wars/web test`：10 个文件、30 个测试通过。
- `pnpm --filter @orbit-wars/web build`：生产构建通过。
- `npx @pureforge/smooth check refine-replay-planet-labels`：Smooth 产物、全仓 lint 和 typecheck 通过。
- 本地 API 与 Web 已恢复在 `8000`、`3003`；浏览器自动刷新因本地 URL 安全策略被拒绝，未绕过策略。

## 疑问

- 无阻塞项；用户已明确更正为“不展示”，不是“不保存”。
