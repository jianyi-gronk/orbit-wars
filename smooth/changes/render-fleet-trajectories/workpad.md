# 工作台

## 计划

- [ ] 恢复 replay frame 的 fleets
- [ ] 绘制在途舰队、短尾迹和兵力
- [ ] 真实回放与自动化验证

## 验收标准

- 有舰队帧可见蓝/红舰标、朝向、短尾迹和兵力。
- 逐帧重建不会遗留已消失舰队。
- 不修改历史回放格式。

## 验证

- 单元测试覆盖 fleets checkpoint、delta 继承和空数组清空。
- 指定 replay 的 segment 20/40 数据抽样。
- Web lint、typecheck、test、build 与本地页面检查。

## 备注

- 根因不是数据缺失，而是 Web 重建器和 BattleStage 未消费 `frame.fleets`。
- 轨迹采用短尾迹，不伪造目标星球连线。

## 疑问

- 无阻塞项。
