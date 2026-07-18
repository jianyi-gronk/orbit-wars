# 踩坑记录

## `overflow-x: hidden` 不代表布局没有横向溢出

- 症状：页面没有可见横向滚动条，但桌面首页 `scrollWidth` 仍比 `clientWidth` 多 91px。
- 根因：固定星场使用负 `inset` 扩大真实布局边界。
- 如何被发现：浏览器验收直接比较首页容器的 `scrollWidth` 与 `clientWidth`，再定位越界节点。
- 修复 / 预防：星场恢复 `inset: 0`；视觉纵深交给增强画布。响应式验收同时检查数值溢出，不只看滚动条。
- 这能改进 harness 吗：是 — 浏览器视觉验收应固定采集横向溢出差值。

## 通用场景转场选择器覆盖局部透明度

- 症状：旧雷达和网络图比预期更亮，遮住了共享三维世界。
- 根因：`.home-scene > *:not(.scene-corners)` 的选择器优先级高于 `.network-map` 和 `.orbital-radar`。
- 如何被发现：截图与预期不一致后读取实际 computed opacity，发现值仍为 1。
- 修复 / 预防：对 active 场景使用同级或更高优先级的局部选择器；视觉验收不要只读样式源码，应检查 computed style。
- 这能改进 harness 吗：是 — 视觉层级检查需要同时采集截图和关键 computed style。

## 英文固定单行标题在窄屏被裁切

- 症状：390px 英文首页的 `COMMAND THE ORBIT` 右侧被裁切，但容器横向溢出仍显示为 0。
- 根因：标题使用 `white-space: nowrap`，中英文共用的移动端字号只适合更紧凑的中文行长。
- 如何被发现：英文窄屏截图；元素外框数值本身不能反映内部文本绘制范围。
- 修复 / 预防：为英文首屏提供更紧凑的语言相关字号，并使用 `Range.getBoundingClientRect()` 核对实际文本绘制范围。
- 这能改进 harness 吗：是 — 双语页面必须分别做窄屏截图，不能用中文结果代替英文。

