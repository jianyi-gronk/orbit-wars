# 验证

日期：2026-07-18

## 代码审查

- [x] 改动范围限定在首页体验、首页专用依赖、质量测试和 Smooth 产物，没有修改回放、竞技场、部署或 Agent 对战业务。
- [x] Three.js 通过客户端动态 `import()` 加载，Canvas 标记为 `aria-hidden`、`tabIndex={-1}` 且不接收指针事件，不阻塞 DOM 首屏或焦点顺序。
- [x] 四幕复用同一 renderer 和场景对象，只更新目标状态；高频指针值通过 ref 读取，不触发整页 React 重渲染。
- [x] 标签页隐藏时取消动画帧，恢复后按动效偏好重启；卸载时清理监听器、geometry、material、render list、renderer 和 WebGL context。
- [x] 初始化异常仅在开发环境告警，CSS 星场、内容和操作继续可用。
- [x] 未引入外部模型、贴图或星球大战版权资产，视觉由程序化几何和项目现有设计语言组成。

## 自动化检查

- [x] `npx @pureforge/smooth check immersive-orbital-visuals` — `smooth-artifacts` 与项目 lint 通过。
- [x] `pnpm --filter @orbit-wars/web test` — 10 个测试文件、28 个测试全部通过。
- [x] `pnpm --filter @orbit-wars/web typecheck` — TypeScript 检查通过。
- [x] `pnpm --filter @orbit-wars/web lint` — ESLint 检查通过。
- [x] `pnpm --filter @orbit-wars/web build` — Next.js 16.2.10 生产构建与 13 个静态页面生成通过。
- [x] `git diff --check origin/main` — 无空白或补丁格式问题。

## 证据

- 中文桌面 `/zh`（1280×720）：首屏 CTA 完整可见；Canvas 实际像素为 1920×1080；首页横向溢出为 0。
- 英文桌面 `/en`（1280×720）：主标题与 CTA 均在视口内；首页横向溢出为 0。
- 中文与英文窄屏（390×844）：主标题、说明、CTA 和次行动均可见；Canvas 调整为 390×844；首页横向溢出为 0。
- 通过四个场景按钮依次进入第 2、3、4 幕，`data-active-scene` 和内部滚动位置同步变化，场景内容在转场后恢复完整清晰度。
- 实际路由页面存在 `canvas.orbital-world` 且尺寸非零，证明动态增强层已在浏览器成功初始化。
- 中文窄屏最终页面控制台的 warning/error 数量为 0。
- reduced-motion 与 WebGL 初始化失败路径由代码审查和静态质量测试覆盖；所选浏览器控制面未提供媒体偏好或 WebGL 禁用模拟，因此未进行浏览器运行时强制模拟。

## 手动验证

首页属于强视觉页面。后续改动时重点快速查看 390px 英文首屏和第 2、3、4 幕，确认长标题、共享世界和旧 HUD 的层级没有回退。

