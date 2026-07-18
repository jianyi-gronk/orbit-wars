# 经验沉淀

## Canvas 视觉验收必须覆盖最终 CSS 叠层

- 来源：pitfalls.md#canvas-上层装饰破坏了太阳完整性
- 适用范围：workflow
- Harness 改进：
  - 类型：workflow-rule
  - 目标：视觉类变更的验证流程
  - 方案：生产构建后对真实页面截图，并同时检查 Canvas、本体容器、伪元素和 overlay 的最终合成效果。
- 机械方案：质量测试可守卫关键 overlay 的透明区，但审美层次仍需要截图判断。

