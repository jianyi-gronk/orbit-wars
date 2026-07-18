# 工作台

## 计划

- [x] 确认 replay 元数据存在
- [x] 定位 compact 或 segment 的实际失败点
- [x] 修复历史回放读取闭环
- [x] 使用指定 replay ID 做浏览器回归

## 验收标准

- 指定旧回放可完整载入。
- 历史接口只暴露实际可读取的回放。
- 新比赛的回放持久化测试继续通过。

## 验证

- 检查指定 ID 的 compact 与全部 checkpoint。
- 运行 API replay、worker persistence 与 web replay 测试。
- 浏览器刷新指定链接并确认播放器、帧数和控制台。

## 备注

- 指定 replay 的 compact、0–160 checkpoint、对象工件经 API 和 Node fetch 全部返回 200 且结构有效。
- 最后分段包含 160–167 帧和一条无 `frame` 字段的 `result` 记录；旧重建器把所有非 checkpoint 记录都当成 delta，读取 `result.frame.step` 时抛出 TypeError。
- 修复后指定回放加载 168/168 帧，播放按钮可把 STEP 000 推进到 STEP 003，浏览器无 error 日志。
- 每个内聚修复独立 commit，全部验证后统一 push。

## 疑问

- 无阻塞项；根因是前端未兼容持久化格式中的终局 `result` 记录，不是历史数据或对象存储丢失。
