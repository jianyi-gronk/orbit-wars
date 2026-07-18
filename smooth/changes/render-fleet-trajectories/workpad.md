# 工作台

## 计划

- [x] 恢复 replay frame 的 fleets
- [x] 绘制在途舰队、短尾迹和兵力
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
- 通用按钮 hover 金色文字会覆盖金色主按钮前景色；主播放按钮已增加更高优先级的深色 hover/focus 规则。

## 疑问

- 自动浏览器此前拒绝本地 URL reload，不能绕过该策略；生产服务已重启，当前标签页手动刷新后即可补视觉确认。

## 结果

- 指定 replay：STEP 20 / 40 / 83 分别包含 5 / 8 / 43 支权威在途舰队。
- Web：32 个测试、lint、typecheck、production build 通过。
- 全仓：Smooth 产物、lint、typecheck、JS/Python 测试通过；Python 165 passed、5 skipped。
- 本地生产 Web `3003` 与 API `8000` 正在监听，页面和 compact API 均返回 HTTP 200。
