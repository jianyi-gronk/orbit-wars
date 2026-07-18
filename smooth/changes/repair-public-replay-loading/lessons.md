# 经验沉淀

## 回放消费者必须按持久化协议处理终局元数据

- 来源：pitfalls.md#回放分段不只包含帧记录
- 适用范围：code-generation | project-check | workflow
- Harness 改进：
  - 类型：project-check
  - 目标：replay writer 与 web reconstruct 的契约测试
  - 方案：用包含 checkpoint、delta、result 的完整末段 fixture 验证帧数、最后 step 和终局元数据互不干扰。
- 机械方案：在前端单元测试中加入 `result` 尾记录，并在集成检查中比较 compact.frameCount 与所有 segment 重建后的帧数。

