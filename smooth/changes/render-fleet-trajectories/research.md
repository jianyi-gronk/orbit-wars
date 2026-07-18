# 前置调研

## 调研问题

- 回放数据是否保存了在途舰队与移动方向。
- 当前播放器在哪一层丢失了舰队信息。

## 已验证事实

- replay checkpoint/delta 的 `frame.fleets` 已保存舰队 ID、阵营、坐标、角度、来源星球和兵力。
- 指定回放在 STEP 20 有 5 支在途舰队，STEP 40 有 8 支，后续帧坐标连续变化。
- `apps/web/src/replay.ts` 当前只把 `planets` 重建进 `ReplayFrame`，完全忽略 `fleets`。
- `BattleStage` 当前只接收并绘制星球与手动瞄准线。

## 风险与约束

- 舰队没有目标星球字段；游戏采用角度发射并由碰撞裁定，不能伪造“连接目标星球”的路线。
- delta 未包含 `fleets` 时必须继承上一帧；显式空数组则表示当前没有在途舰队。
- 密集战场可能同时存在十余支舰队，轨迹应使用短尾迹，避免全屏长线遮挡星球。

## 对产品讨论的启发

- 采用“权威当前位置 + 朝向舰标 + 短尾迹 + 当前兵力”的表现，准确表达移动而不推断不存在的目标。
- 蓝、红双方沿用现有阵营色，舰队 ID 不面向观众展示。

## 来源与证据

- `services/match-worker/orbit_match_worker/replay/writer.py`
- `packages/orbit-engine-py/orbit_engine/schema.py`
- `apps/web/src/replay.ts`
- 指定公开回放的本地 segment 20、40 API 响应。

