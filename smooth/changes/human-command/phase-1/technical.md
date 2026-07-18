# 技术设计

## 架构总览

```text
Arena（feature flag）──> Human training match + scoped ticket
                              ↓
LiveBattle ── WebSocket ──> ws_matches ── Redis streams ──> MatchWorker
   ├─ direct aim / force / queue        turn.open              │
   ├─ auto empty action                 snapshots              │
   └─ reconnect + resync <──────────── authoritative frames ───┘
```

## 功能列表

1. Human training-only 产品保护。
2. 目标式命令草稿和队列编辑。
3. 自动空过、step 幂等和短回合节奏。
4. WebSocket 重连与权威 resync。
5. 首次教学与训练结果入口。

## 功能：Human 训练保护

- `humanPlayEnabled` 继续作为公开 kill switch。
- API 对 Human `ranked` 请求返回稳定错误；第一阶段只允许 training。
- Match 创建继续生成 slot-scoped ticket，Human participant 不绑定 strategy version。
- 公开历史保留 HUMAN 标签，不拆 matchmaking pool 或 rating 数据结构。

## 功能：命令交互

扩展 `apps/web/src/battle.ts` 纯函数：

- `aimAtPoint()`：从源星和目标画布坐标计算规范化角度。
- `setShipRatio()`：25/50/75/100% 快捷兵力，扣除同源已排队兵力。
- `removeQueuedLaunch()`、`updateQueuedShips()`、`availableShips()`。
- `trajectoryPreview()`：只计算方向射线与 ETA 提示，不宣称最终碰撞结果。

`BattleStage` 继续负责正方形坐标映射，并新增 aim preview 与目标点击回调。LiveBattle 不展示星球 ID，只展示兵力；右侧命令队列可编辑、删除和清空。

## 功能：回合与自动空过

LiveBattle 为每个 `turn.open(step, deadlineAt)` 创建一次 step-scoped submission：

- 用户确认时立即提交当前队列。
- 到 deadline 前安全余量仍未提交时自动发送空 commands。
- `submittedSteps` 防止同 step 重复；新 frame 只清理已提交 step 的草稿。
- 服务器继续以 expectedStep 和 command batch 校验；过期 submission 不进入其他 step。

Worker 默认 Human turn window 调整为 2.5 秒，环境变量仍可覆盖。Agent-only 比赛不等待 Human stream，因此不受影响。

“连接正常但空过”通过自动空 command 记录为有效 submission；WebSocket 断开期间没有 submission，恢复 tracker 才会累计 missed。训练达到宽限上限时 forfeit，不结算 rating。

## 功能：重连与 resync

LiveBattle 将连接建立抽为可取消状态机：

- 非主动 close 后按 0.5s/1s/2s/4s 上限退避重连。
- 使用 sessionStorage ticket 重建连接，open 后发送 `match.resync(lastSeenStep)`。
- 收到 snapshot/frame 更新 `lastSeenStep`；旧 step 事件忽略。
- 页面卸载主动 close，不触发重连。
- ticket 无效或比赛结束停止重试并给出可操作返回链接。

## 功能：首次教学

教学状态仅存当前账户浏览器 localStorage，不影响服务端战绩。Arena 在首次选择 Human 时先展示四步交互说明；用户完成或明确跳过后才创建真实训练赛。教学不伪造比赛结果。

## 技术验收标准

- Human ranked 在 UI/API 双层不可创建，Agent ranked 不受影响。
- 点选目标产生与画布坐标一致的角度；快捷比例和队列编辑永不超出可用库存或六条上限。
- 每个 Human step 最多一个 command batch；自动空过不会被判作 disconnect。
- 重连后只显示最新私有快照，过期事件和命令不污染当前 step。
- 训练 forfeit 不产生 rating event，完整比赛仍生成 replay 和 HUMAN 归因。
- feature flag false 时公开页面和 bundle 不出现 Human 主入口。

