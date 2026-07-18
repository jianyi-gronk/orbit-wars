# 工作台

## 计划

- [x] 确认 replay 元数据存在
- [x] 定位 compact 或 segment 的实际失败点
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

- 指定 replay 的 compact、0–160 checkpoint、对象工件经 API 和 Node fetch 全部返回 200 且结构有效。
- in-app Browser 对 `/orbit-api/...` 返回 `ERR_BLOCKED_BY_CLIENT`；当前 apiFetch 默认使用这个路径，因此页面只得到无状态的网络异常。
- 修复方向是把默认同源代理改为 `/gateway`，同时保留旧路径兼容已有部署。
- 每个内聚修复独立 commit，全部验证后统一 push。

## 疑问

- 无阻塞项；根因已定位为客户端代理路径被浏览器拦截，不是历史数据或对象存储丢失。
