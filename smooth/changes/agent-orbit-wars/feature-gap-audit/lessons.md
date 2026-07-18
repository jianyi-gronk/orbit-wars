# 经验沉淀

## 游戏闭环必须验证到玩家能提交第一条有效指令

- 来源：pitfalls.md#模块测试通过不代表用户真的能开一把
- 适用范围：workflow
- Harness 改进：
  - 类型：workflow-rule
  - 目标：游戏类变更的验收模板
  - 方案：将“角色创建、获取对手、创建比赛、worker 消费、实时快照、首条指令确认”列为一个不可拆分的关键旅程。
- 机械方案：本地 smoke 脚本负责 API/队列状态，浏览器检查负责主按钮、倒计时和 `turn.accepted` 可见证据。

## 按消息 discriminator 更新状态，不用共有字段推断完整协议

- 来源：pitfalls.md#实时-snapshot-与-frame-不能按同一形状覆盖
- 适用范围：code-generation
- Harness 改进：
  - 类型：generation-rule
  - 目标：实时协议客户端生成规则
  - 方案：对 discriminated union 强制穷尽分支，每个分支只更新其拥有的字段，并为身份/时钟等持久状态写回归测试。
- 机械方案：TypeScript 使用生成的 union + exhaustive switch；禁止把部分消息断言为完整 Observation。

## 替换页面实现时同步审计源码路径型测试

- 来源：pitfalls.md#质量检查曾绑定已废弃-demo-页面
- 适用范围：project-check
- Harness 改进：
  - 类型：project-check
  - 目标：UI 页面替换检查
  - 方案：移动或重定向页面后，搜索 `readFileSync`、snapshot 和路径字符串，确保质量门禁指向新的产品组件。
- 机械方案：`rg 'readFileSync|旧页面路径' apps/web/src`。
