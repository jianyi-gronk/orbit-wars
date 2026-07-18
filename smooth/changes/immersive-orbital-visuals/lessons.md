# 经验沉淀

## 强视觉双语首页需要同时验证布局数值、computed style 和截图

- 来源：pitfalls.md#overflow-x-hidden-不代表布局没有横向溢出、pitfalls.md#通用场景转场选择器覆盖局部透明度、pitfalls.md#英文固定单行标题在窄屏被裁切
- 适用范围：workflow | project-check | guidance
- Harness 改进：
  - 类型：workflow-rule
  - 目标：首页与营销页视觉验收流程
  - 方案：桌面与 390px 下分别检查中英文截图、`scrollWidth - clientWidth`、关键层 computed opacity 和长文本真实绘制范围，并检查控制台错误。
- 机械方案：浏览器只读脚本统一返回 viewport、overflow delta、Canvas 尺寸、CTA rect、长文本 Range rect 与关键 computed style。

