# 技术设计

## 架构总览

```text
RootLayout
  ├─ GlobalInteractionFX        全站 pointer 点击能量层
  └─ LocalizedPage
       ├─ SiteHeader            三个一级入口 + MissionMenu
       └─ HomeExperience        首页四幕滚动容器
            ├─ wheel/keyboard controller
            ├─ IntersectionObserver
            └─ CSS scene states + pointer parallax
```

不改变 API、路由或业务数据。首页交互作为独立客户端岛接入现有服务端路由，其他业务页继续服务端渲染并复用原组件。

## 共享动效边界

- `src/home-motion.ts` 保存纯函数场景索引计算，保证滚轮只能移动到相邻合法场景并可单元测试。
- 动效只使用 `transform`、`opacity` 和 CSS 自定义属性，避免在滚动期间修改布局属性。
- 客户端通过 `matchMedia("(prefers-reduced-motion: reduce)")` 决定是否注册滚轮接管和指针视差；CSS 同时提供最终兜底。
- 点击反馈层设置 `pointer-events: none`，在 `pointerdown` 后立即绘制，不阻止链接导航、表单提交或按钮事件。

## 首页场景控制

### 涉及文件

- `components/product/HomeExperience.tsx`
- `src/home-motion.ts`
- `app/game-ux.css`
- 本地化 catch-all 首页路由

### 状态与行为

- `activeScene`：当前场景索引。
- `data-scene-state="before|active|after"`：由索引关系推导，驱动退场和登场样式。
- 桌面 wheel 使用非 passive 监听器；超过阈值后调用相邻场景的 `scrollIntoView`，一次输入只推进一幕，并用短锁防止触控板惯性连续跳过。
- `IntersectionObserver` 以 0.6 阈值同步触控滚动后的 activeScene。
- ArrowUp/ArrowDown、PageUp/PageDown、Home/End 走同一 `goToScene`。
- 右侧场景轨道提供四个具名按钮，可直接定位且暴露 `aria-current`。
- 指针移动只更新容器 `--pointer-x/--pointer-y`，CSS 将其用于星层和雷达轻量视差。

### 设计决策

- 选择“原生滚动容器 + scroll snap + 相邻导航”，不选择完全虚拟化的绝对定位轮播。前者保留触控、浏览器滚动语义和无 JavaScript 降级，滚动陷阱风险更低。
- 固定四幕，不把业务内页放进首页滚动控制；首页负责讲清主循环，业务页负责完成任务。

## 紧凑任务导航

### 涉及文件

- `components/product/SiteHeader.tsx`
- `app/game-ux.css`

### 行为

- 一级链接固定为 Arena、Ranking、Command。
- `MissionMenu` 使用原生 `details/summary`，承载 History、Agent Guide、About、Q&A、Updates；无需额外弹层状态即可支持键盘、点击外部后的原生关闭语义和无 JavaScript可用性。
- 当前一级路由通过 `usePathname` 设置 `aria-current="page"` 与 HUD active 样式。
- SessionAction 和 LocaleSwitcher 保持独立，不改变认证流程。

## 全局点击反馈

### 涉及文件

- `components/product/GlobalInteractionFX.tsx`
- `app/layout.tsx`
- `app/game-ux.css`

### 行为

- document 级 `pointerdown` 只响应最近的 `a`、`button` 或 `[role="button"]`。
- 每次点击生成一个最多存在 620ms 的固定定位 pulse，包含中心闪光与两道扩散轨道；同时给目标附加短暂 `data-pressed` 状态。
- reduced motion 下组件不创建 pulse，仅保留浏览器原生 focus/active 反馈。

## 视觉层

- 首页使用舰桥框线、坐标刻度、扫描带、星图噪点、雷达圆环与纯 CSS 舰队航迹，不引入第三方图像资产。
- 内页通过 body 背景、header 框架、button/panel 边角与 hover/active 状态共享游戏化语言；保持现有正文对比度和表单密度。
- 所有装饰元素 `aria-hidden`，页面标题和 CTA 保持语义结构。

## 技术验收标准

- wheel 一次最多改变一个 scene，首尾索引被 clamp。
- 四个 scene 均可由键盘和指示器访问；active scene 暴露 `aria-current`。
- reduced motion 不注册 wheel preventDefault，不执行 pointer parallax 或 pulse 动画。
- 点击 pulse 不改变目标尺寸、不截获指针、不延迟导航。
- 390px 页面 `scrollWidth === clientWidth`；桌面首页场景高度与视口对齐。
- Web lint、typecheck、Vitest、生产 build 通过。
