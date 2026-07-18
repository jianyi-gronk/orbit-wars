# 工作台

## 计划

- [x] 固化太阳中心与半径
- [x] 绘制规则一致的太阳危险区
- [x] 构建、重启并推送

## 验收标准

- 太阳中心为 `(50, 50)`，规则半径为 `10`。
- 太阳不再被误认为普通背景同心圆。
- 舰队和星球继续绘制在太阳之上。

## 验证

- 单元测试检查规则常量。
- Web lint、typecheck、test、build。
- 本地页面和指定 replay compact 返回 HTTP 200。

## 备注

- 太阳是隐式规则障碍，不存在于 replay frame 中，因此由固定规则集常量渲染。

## 疑问

- 无阻塞项。

## 结果

- Web 33 个测试、typecheck、lint 和 production build 通过。
- Smooth 产物、全仓 lint 和 typecheck 通过。
- 本地生产 Web 3003 与 API 8000 正在监听；页面和指定 replay compact 均返回 HTTP 200。
