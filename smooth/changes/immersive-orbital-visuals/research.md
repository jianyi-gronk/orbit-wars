# 沉浸式轨道视觉调研

日期：2026-07-18

## 调研问题

如何参考 HTML-in-Canvas 与 Three.js 的视觉表现，让 Orbit/Wars 更像一个正在运行的星际游戏，同时保持中英双语、可访问性、移动端性能和原创性？

## 已验证事实

- HTML-in-Canvas 展示了把实时 DOM/HTML 内容作为 WebGL 纹理使用，并叠加 CRT、色差、折射、液态玻璃和像素消散等效果的实验方向。
- 它依赖仍处于实验阶段的 `drawElementImage()`、`layoutsubtree` 和 `paint` 事件；当前需要 Chromium 147+ 并开启实验特性，不适合成为公开网站的核心运行依赖。
- Three.js 官方示例覆盖 WebGL、CSS3D 与混合渲染，可用于构建稳定的程序化 3D 背景；用户提到的 `tree.js` 按语境理解为 Three.js。名为 tree.js 的项目主要处理树数据结构，与视觉目标不符。
- 当前首页已经具备四幕全屏滚轮叙事、键盘切换、移动端布局和 reduced-motion 降级，但主要依赖 CSS 星图、雷达与网格装饰，场景之间缺少一个持续存在的三维世界。
- 当前战斗画面已使用 PixiJS；首页尚未引入 Three.js。

## 当前代码链路

- 首页交互入口：`apps/web/components/product/HomeExperience.tsx`
- 首页与游戏视觉：`apps/web/app/game-ux.css`
- 全局产品样式：`apps/web/app/product.css`
- 战斗渲染：`apps/web/components/battle/BattleStage.tsx`（PixiJS）

## 可借鉴的设计语言

以下内容作为产品灵感，不直接复制参考站布局或素材：

- 保留真实 DOM 作为内容与交互层，在其后增加持续运行的程序化轨道世界。
- 滚轮切幕时不只移动文案，同时改变镜头距离、星球方位、航线密度与阵营色温，让四幕像同一次飞行。
- 把扫描线、色差、玻璃折射等效果控制在短促转场和装饰层，不牺牲文字清晰度。
- 使用程序化几何体、粒子、轨道与信标，避免依赖外部版权模型，也避免明显复刻参考站。
- 所有核心入口、双语文本与焦点顺序继续由 DOM 承担；Canvas 仅作为 `aria-hidden` 的增强层。

## 推荐技术方向

1. 新增一个独立的 `OrbitalWorld` 客户端组件，动态加载 Three.js，作为首页四幕共享的背景画布。
2. 通过 `activeScene` 驱动镜头、星球、轨道、节点和颜色的目标状态，并做插值过渡。
3. 对设备像素比设上限；页面不可见时暂停；卸载时释放材质、几何体与 renderer。
4. reduced-motion 下禁用持续运动，只渲染静态构图；WebGL 初始化失败时保留现有 CSS 背景。
5. 不调用 HTML-in-Canvas 的实验 API，保留未来渐进增强的可能。

## 风险与约束

- Three.js 会增加首页包体，应动态加载并限制只在首页使用。
- Canvas 不得遮挡链接、按钮或破坏双语排版。
- 小屏幕需降低粒子数量与像素比，避免发热和掉帧。
- 视觉增强不得改变现有 Agent-only 主流程，也不能重新增加过多一级 Tab。
- 必须保留 `prefers-reduced-motion` 与无 WebGL 降级路径。

## 资料来源

- https://html-in-canvas.dev/
- https://html-in-canvas.dev/demos/
- https://threejs.org/examples/?q=3d
- https://jangdan.github.io/tree.js/
