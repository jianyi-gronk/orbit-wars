# 踩坑记录

## 模块测试通过不代表用户真的能开一把

- 症状：API 能创建 `QUEUED` 比赛，Web 也能进入战术台，但页面一直停在“等待战场快照”；同时已有舰队的用户仍看到“创建舰队”。
- 根因：实现和验收按 API、页面、引擎模块分别完成，没有运行真实队列消费者，也没有把首次用户从首屏走到回合提交。
- 如何被发现：用户直接指出“进来不知道怎么创建开一把”，随后用浏览器走完整链路才复现。
- 修复 / 预防：增加真实 Redis match worker；所有主入口按会话/舰队状态切换；验收强制覆盖 create → offer → match → WebSocket snapshot → command accepted。
- 这能改进 harness 吗：是 — 游戏产品不能以“路由 200 + API 测试”代替端到端可玩性证据。

## 实时 snapshot 与 frame 不能按同一形状覆盖

- 症状：收到 `match.frame` 后若直接覆盖完整 Observation，会丢失当前 player 与 deadline，槽位 1 可能被错误当成槽位 0。
- 根因：`match.snapshot.payload` 是 `ObservationV1`，`match.frame.payload` 是 `ReplayFrameV1`，两者都有 planets/step 但语义和字段集合不同。
- 如何被发现：最终协议代码审查逐项对照 WebSocket contract。
- 修复 / 预防：snapshot 初始化身份，frame 只合并权威帧字段，`turn.open` 单独更新时间窗；质量测试继续检查实时战术面板。
- 这能改进 harness 吗：是 — 实时协议生成应要求按 discriminator 分支处理，不能只按共有字段做 duck typing。

## 质量检查曾绑定已废弃 demo 页面

- 症状：真实战术台替代 demo 后，全量测试仍读取 `app/battle/demo/page.tsx` 查找键盘和 ARIA 文案。
- 根因：质量门禁绑定文件路径而非当前产品组件。
- 如何被发现：`pnpm check` 的 quality test 失败。
- 修复 / 预防：检查改为读取 `LiveBattle.tsx`，同时要求中英文键盘说明与战术面板名称。
- 这能改进 harness 吗：是 — 页面替换任务应同步搜索读取源码路径的测试。
