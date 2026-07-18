# 工作台

## 计划

- [x] 确认 replay 元数据存在
- [ ] 定位 compact 或 segment 的实际失败点
- [ ] 修复历史回放读取闭环
- [ ] 使用指定 replay ID 做浏览器回归

## 验收标准

- 指定旧回放可完整载入。
- 历史接口只暴露实际可读取的回放。
- 新比赛的回放持久化测试继续通过。

## 验证

- 检查指定 ID 的 compact 与全部 checkpoint。
- 运行 API replay、worker persistence 与 web replay 测试。
- 浏览器刷新指定链接并确认播放器、帧数和控制台。

## 备注

- 基础 replay 元数据端点当前返回 200，需继续检查 compact 和 0–160 checkpoint。
- 每个内聚修复独立 commit，全部验证后统一 push。

## 疑问

- 失败是对象存储工件读取、segment 边界，还是前端串行加载期间的瞬时失败，待实测确认。
