# 前置调研

## 调研问题

- 截至 2026-07-19，Orbit Wars 完成首轮 Agentank 对齐后，下一批最值得优化的产品机制是什么？
- 哪些差距会直接影响用户信任、复盘意愿和 Agent 持续迭代，哪些只是活跃度起来后的外围系统？
- 哪些 Agentank 机制可以转译为 Orbit Wars 的原创星战表达，而不增加一级导航或恢复 Human 手动玩法？

## 已验证事实

### Agentank 当前产品机制

- 首页不只解释三步 Agent 循环，还直接展示玩法规则、技能差异、最新公开战斗和再次开始入口。
- 历史页把每场比赛压缩成观众可读信息：胜负标记、双方、地图、结束原因、时间、Heat 和回放入口，并支持 `Exciting only`。
- 今日、本周榜单可按胜率、胜场和精彩度排序；历史榜使用 rank score。排名周期与排序含义保持一致。
- 坦克详情页提供“复制关键信息”，把 Tank Key 与 Agent Guide 作为一次交接；详情页同时呈现当前代码、版本、历史和下一步。
- Agent API 返回当前 standing、合适对手、近期真实比赛、冷却时间和建议下一动作；真实挑战返回人类回放与 Agent JSON。
- Agent replay JSON 不只是原始帧，还包含 shots、movement、stars、skill usage 和短诊断等紧凑战术摘要。
- Agentank 已扩展 TankBook 赛后评论、每日战报、团队榜、Cups、成就、邀请、商店和战场样式；这些属于留存与社区层，不是基础闭环的必要条件。

### Orbit Wars 当前产品机制

- 已完成状态感知页头主行动、首页真实回放首段、最近三场公开对局和回放一键交给 Agent 分析，基础循环已明显对齐。
- Command Center 的主卡片仍固定显示“让 Agent 出战”，没有根据无 Key、无 ready 版本或刚结束比赛改变；生成 Key 后仍只能分别复制密钥和打开 Guide，没有一次性 Agent 交接包。
- 历史卡片优先展示 schema 版本、帧数、工件大小和保存时间；胜负、rating delta 和双方策略存在，但缺少可比较的观战强度、关键转折和高光入口。
- `featured` 当前只判断回放 analysis payload 是否存在 events；这不能区分普通比赛与真正精彩比赛，可能导致“精彩对局”筛选几乎等于“有分析数据”。
- 榜单 API 无 `sort` 参数。今日和本周只过滤活跃比赛，但仍按舰队长期 `displayScore` 排序；UI 把它显示为今日/本周榜，周期含义容易被误解。
- 榜单只提供周期和控制标识筛选，没有胜率、胜场、近期表现或精彩度排序，也没有“距离下一段位”反馈。
- 公开舰队页有近期比赛和版本谱系，但版本只展示 ID、状态和来源；看不到版本备注、submittedBy、版本战绩、rating 贡献和代表回放。
- Arena 只给一个自动匹配对手，展示分差、近期重复和 multiplier；没有对手战绩、段位、策略风格、推荐原因的可读解释，也没有刷新或备选对手。
- 回放 Agent 交接已能复制 compact 数据、事实和事件，但站内尚未保存 Agent 的赛后结论，也没有把“分析 → 新版本 → 再战”的结果串成可见版本故事。

## 当前差距与机会

### 第一优先级：竞技信息必须可信、可读

1. **重做周期榜单语义与排序**
   - 今日/本周应按周期内胜率、胜场或近期表现排序；历史榜继续按总分。
   - 如果暂时不做多排序，至少明确写成“今日活跃舰队（按总分）”，不能让用户误以为是今日战绩榜。
   - 同时显示比赛场次，低样本胜率要有最低场次或置信保护。

2. **把历史卡片从工件清单改成观战卡片**
   - 主层级：W/L、双方、段位、rating delta、结束原因、时间。
   - 次层级：2～4 个关键事件和可跳转高光；schema/大小/保存时间折叠为“验证详情”。
   - 设计可解释的 `intensityScore`，建议使用领先变化次数、星球易手、淘汰、rating swing、比赛时长和逆转信号，避免直接复制 Heat 名称。

### 第二优先级：让 Agent 接入和迭代真正省一步

3. **Command Center 一键 Agent 交接包**
   - Key 生成当下提供“复制全部”：API Base、Guide、Key、舰队 ID、推荐首条指令。
   - 明文仍只出现一次；离开后不再恢复。
   - Command Center 的 NEXT 卡片与页头共用同一状态模型，而不是固定“出战”。

4. **版本级成长故事**
   - 每个策略版本展示 notes、submittedBy、状态、最近战绩、rating 净变化和代表回放。
   - 提供“与上一版比较”：胜率、平均控制星球、平均兵力领先时长、关键事件变化。
   - 回放交给 Agent 后，下一次发布允许关联来源 replay ID，使用户能看到“这次失败促成了 v12”。

### 第三优先级：提高下一场比赛的决策质量

5. **对手选择升级为推荐，而不是黑盒匹配**
   - 保留默认唯一推荐，增加“换一个”而不是复杂搜索页。
   - 推荐卡展示对手段位、近期战绩、风格、分差、重复次数和一句本地化原因。
   - 给 Agent API 返回同样的推荐原因与风险，保证人和 Agent 看到同一事实。

6. **站内赛后任务链**
   - 回放结束后明确三步：复制分析包 → 发布新版本 → 用同类对手验证。
   - Command Center 显示最近一场比赛和当前版本是否在赛后更新过，避免用户不知道迭代是否完成。

### 活跃度起来后再做

- 每日战报与站内通知。
- Agent 赛后一句话、舰队留言墙等轻社交。
- 团队榜、Cups、成就、邀请和装饰收集。
- 多地图和可选舰队能力；它们会改变平衡与回放协议，应独立立项。

## 暂不建议跟进

- **恢复网页代码编辑器**：Orbit Wars 已明确 Agent-only，网页编辑会重新模糊产品角色。
- **增加一级导航**：现有竞技场、榜单、指挥中心已经足够，历史和指南继续留在任务菜单。
- **商店、钱包和奖励经济**：当前更需要证明用户会持续复盘和发布版本。
- **直接复制 Heat**：没有可解释公式就只会形成看似精确的装饰数字。
- **马上做团队/Cups**：单舰队版本成长尚未形成可读故事，提前扩张会稀释核心。

## 风险与约束

- 周期榜单的胜率排序必须处理样本量，否则 1 胜 0 负会长期压过高质量活跃舰队。
- intensityScore 必须由权威事件计算并公开解释，不应用生成式模型打分。
- 版本统计需要按比赛锁定的 strategyVersionId 归因，不能按舰队当前版本回填历史。
- Agent 交接包只能在密钥生成时包含明文 Key，且不得写入日志、回放或公共页面。
- 对手推荐不能鼓励刷分；需要继续尊重近期重复和 rating multiplier 规则。

## 对产品讨论的启发

- 下一轮最值得围绕“**让一场比赛变得值得看，并能证明下一版真的更强**”定义需求。
- 推荐默认范围为三件事：榜单语义与排序、观众化历史卡片、Command Center 一键交接包。
- 版本级对比是紧随其后的高价值功能，但涉及统计聚合和 replay 归因，适合单独作为第二批。
- 社区、团队和奖励系统都应以真实复盘率、版本发布率和再战率为前置指标。

## 来源与证据

- Agentank 首页（访问日期 2026-07-19）：https://agentank.ai/
- Agentank About / Rulebook（访问日期 2026-07-19）：https://agentank.ai/about
- Agentank 历史页（访问日期 2026-07-19）：https://agentank.ai/history
- Agentank Agent Guide（访问日期 2026-07-19）：https://agentank.ai/agent-guide
- Agentank Rank system update（访问日期 2026-07-19）：https://agentank.ai/updates/2026-05-14-rank-system?lang=en
- Orbit Wars 指挥中心：`apps/web/app/command/CommandCenter.tsx`
- Orbit Wars 榜单与历史：`apps/web/components/product/PublicCompetition.tsx`
- Orbit Wars 竞技场：`apps/web/app/arena/ArenaForm.tsx`
- Orbit Wars 公开竞技 API：`services/api/orbit_api/api/leaderboard.py`
- Orbit Wars Agent API：`services/api/orbit_api/api/agent.py`
- Orbit Wars 回放交接：`apps/web/components/battle/ReplayPlayer.tsx`
