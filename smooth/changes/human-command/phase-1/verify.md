# 验证记录

日期：2026-07-19

结论：代码能力通过，公开开关保持关闭。Human 指挥仍是待确认的训练 Beta，不进入排位。

## 自动化证据

- API 明确拒绝 Human ranked，并保持 Agent ranked 正常创建。
- Worker 默认 Human 回合窗口为 2.5 秒；Agent-only 对局不引入等待。
- Web 纯函数测试覆盖点击/拖拽瞄准、兵力比例、可用库存、队列编辑与删除、每 step 一次提交、自动空过和重连状态。
- `pnpm check`、Python 全量测试、typecheck、lint 与 production build 全部通过。

## 浏览器证据

- `NEXT_PUBLIC_ENABLE_HUMAN_PLAY=false`：中文 Arena 与创建入口只展示 Agent，站内策略路径正常，无 Human 公开入口。
- 临时使用 `NEXT_PUBLIC_ENABLE_HUMAN_PLAY=true`：中文和英文均可选择 Human，展示四步教学，并锁定为训练模式；排位与模式切换不可选。
- Human 战术台已展示星球内部兵力、点击/拖拽目标预览、兵力快捷档、命令队列与双语连接状态。
- 验收结束后重新以 false 构建并启动最终站点，没有公开启用 Human 功能。

## 待产品确认

- 首发是否只开放“Human 对平台 Agent”的训练 Beta。
- 移动端触控与窄屏达到什么标准后才允许公开入口。
- 逃跑判定、训练中断指标与 Beta 退出条件的最终产品规则。
