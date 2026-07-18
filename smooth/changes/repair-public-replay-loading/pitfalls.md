# 踩坑记录

## 回放分段不只包含帧记录

- 症状：前 160 帧可以渐进显示，但最后一个分段加载后整页变成“无法加载该对局”。
- 根因：writer 在末尾写入无 `frame` 字段的 `result` 记录；前端类型只声明 checkpoint/delta，并把所有非 checkpoint 记录都按 delta 读取。
- 如何被发现：先验证所有 API 分段为 200，再在错误面板记录失败阶段与异常类型，定位到 `SEGMENT 160 / Cannot read ... step`，最后检查该分段记录类型。
- 修复 / 预防：重建器显式分支 checkpoint/delta，其他记录跳过；测试必须包含终局 result 尾记录。
- 这能改进 harness 吗：是 — 回放契约测试应覆盖完整流的所有 record type，而不仅是中间 checkpoint。

## 渐进成功不代表整场加载成功

- 症状：画面一度出现 160 帧，随后错误 catch 把已有画面全部替换为离线面板。
- 根因：串行分段加载中，最后一步异常仍被当成整场元数据不可用。
- 如何被发现：对比旧截图中的部分帧画面和最终离线状态，并逐 checkpoint 验证。
- 修复 / 预防：错误诊断必须带 COMPACT/SEGMENT 阶段；验收要检查 `frames.length === frameCount`，不能只看第一帧出现。
- 这能改进 harness 吗：是 — 公开回放验收应读取最后 checkpoint 并检查完整帧数。

