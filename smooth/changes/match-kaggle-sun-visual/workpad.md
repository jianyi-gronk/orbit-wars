# 工作台

## 计划

- [x] 用 Pixi `FillGradient` 替换旧版多层圆、虚线环和日冕装饰。
- [x] 保留 `SUN_RADIUS` 作为太阳实体半径，并将光晕扩展至约 2.8 倍半径。
- [x] 完成提交和推送。

## 验收标准

- 太阳为完整金黄色实体圆盘，外部是连续柔和的暖色光晕。
- 不再出现虚线环、尖刺、刻度、折线日冕或白色小核心。
- 游戏规则和回放数据不变。

## 验证

- `pnpm --filter @orbit-wars/web test`
- `pnpm --filter @orbit-wars/web typecheck`
- `pnpm --filter @orbit-wars/web build`
- 本地生产服务重启后由实际回放页面进行视觉复核。

## 备注

- 视觉基准是 Kaggle 参考图中的大面积纯金色圆盘和宽柔光，不扩展额外装饰创意。
- Pixi 8.13.2 原生支持径向 `FillGradient`，可避免多层半透明圆产生色带。

## 疑问

- 无。
