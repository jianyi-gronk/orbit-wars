# 工作台

## 计划

- [x] 提炼 AgenTank 的核心产品闭环
- [x] 将现有 orbit-wars 能力映射为用户产品
- [x] 定义第一阶段范围、关键模块和验收标准
- [x] 增加人类直接指挥模式并统一竞技口径
- [x] 确定原创太空歌剧与复古未来军事终端的视觉方向
- [x] 加入大胆的高端时尚编辑式布局方向
- [x] 确认关键产品决策
- [x] 完成技术设计
- [x] 拆分实现任务
- [x] 按 `tasks.md` 实施波次 A：可复现底座
- [x] 按 `tasks.md` 实施波次 B：Agent 与模拟闭环
- [x] 按 `tasks.md` 实施波次 C：实时统一对战
- [x] 按 `tasks.md` 实施波次 D：回放与竞技产品
- [x] 按 `tasks.md` 实施波次 E：公开上线

## 实施进度

- [x] T01：初始化 pnpm/Next.js 与 Python 多包工作区、统一质量脚本和 GitHub Actions CI。
- [x] T02：建立 PostgreSQL、Redis 和 S3 兼容对象存储的本地基础设施。
- [x] T03：建立版本化共享契约生成链。
- [x] T04：建立数据库、身份验证与幂等写入底座。
- [x] T05：提取并固定 Orbit Wars 2P 规则引擎。
- [x] T06：建立确定性 golden 回归套件。
- [x] T07：实现 Match Worker 引擎适配与比赛状态机。
- [x] T08：建立原创设计 token 与组件基线。
- [x] T09：实现账号与单舰队领域 API。
- [x] T10：实现不可变策略版本与对象存储。
- [x] T11：构建固定依赖的 Agent Sandbox。
- [x] T12：实现策略验证流水线与内置基线 Bot。
- [x] T13：实现 Agent Key、Agent API 与 Guide。
- [x] T14：实现模拟训练编排与资源限额。
- [x] T15：实现统一控制器、回合时钟与命令校验。
- [x] T16：实现比赛创建、队列与短期票据。
- [x] T17：实现 WebSocket 网关与实时同步。
- [x] T18：实现人类战术指挥客户端。
- [x] T19：接入 Agent 执行器与加速 Agent 对局。
- [x] T20：实现断线、Worker 恢复与幂等终局。
- [x] T21：实现流式回放写入与版本化存储。
- [x] T22：实现关键事件、指标与事实型胜因。
- [x] T23：实现公开回放 API 与交互播放器。
- [x] T24：实现舰队统一 rating 与幂等结算。
- [x] T25：实现匹配、挑战和反刷分规则。
- [x] T26：实现统一排行榜与公开舰队档案 API。
- [x] T27：实现品牌首页、账号入口与舰队创建闭环。
- [x] T28：实现舰队指挥中心与 Agent 管理体验。
- [x] T29：实现竞技场、模式选择和公开榜单页面。
- [x] T30：建立可观测性、安全与隐私门禁。
- [x] T31：完成跨闭环自动化与故障验收。
- [x] T32：完成性能、无障碍、原创性与发布准备。

## 验收标准

- 用户无需编码即可创建舰队，并选择完成首场手动训练或 Agent 模拟。
- Agent 可以读取舰队上下文、模拟、发布可追溯版本并发起正式挑战。
- 玩家可以选择源星、发射方向和舰船数量亲自指挥战斗。
- 正式战产生排名变化、永久战绩和可分享的逐帧回放。
- 人类与 Agent 共用一个匹配池、计分规则和排行榜，控制方式仅作公开标识。
- 回放能够解释关键事件与最终胜因。
- 第一阶段形成 2P 创建—训练—发布—排位—复盘闭环。
- 产品品牌和视觉资产不依赖第三方影视 IP。
- 视觉具有熟悉的星际战争氛围，但不存在可识别的影视 IP 或 AgenTank 页面复刻。
- 品牌页可大胆采用非对称编辑布局，实时战斗页仍必须保持操作清晰。

## 验证

- 后续验证首页首屏是否能在 30 秒内让新用户说清核心玩法。
- 后续用一名非开发者走通“创建舰队到首场模拟”的可用性测试。
- 后续验证模拟与正式战的数据边界、版本归因和排名一致性。
- 后续验证回放时间轴、事件标记和指标能否解释典型胜负翻转。
- 后续验证人类发令流程能否在命令时限内快速理解和完成。
- 后续验证统一榜单中每场战绩的控制方式和 Agent 版本归因准确。
- 后续验证两种控制方式获得相同信息并遵守相同行动时限。
- 后续进行视觉相似性审查，检查 Logo、字体、舰船轮廓、阵营符号、声音和关键页面构图。
- 后续验证战斗特效不会遮挡归属、兵力、航迹与操作反馈。
- 后续分别验证品牌页的创意辨识度和战斗页的指令效率，避免用同一布局标准评价两类页面。
- 后续验证减弱动态效果时的完整可用性。
- 技术阶段确认现有 orbit-wars 引擎可复用范围、运行隔离和每局成本。
- 后续以固定 seed 和历史回放建立提取引擎的逐步 golden 测试。
- 后续对 Agent Sandbox 做无网络、资源上限、超时和逃逸测试。
- 后续对统一 Observation/CommandBatch 做人类与 Agent 协议一致性测试。
- 后续按 `tasks.md` 的 T01–T32 顺序推进；跨阶段提前实施时必须先满足该任务列出的依赖。
- 每个实施波次结束时运行 Smooth 检查，并把自动化结果或人工验收证据补充到 `verify.md`。
- T01 已通过 `pnpm install --frozen-lockfile`、`pnpm check` 和 Next.js 生产构建；JS 3 项测试、Python 4 项测试全部通过。
- T02 已验证本地与测试两套 Compose 栈独立健康；API/Worker 均探测三项依赖成功，测试 volume 可完整清理且不影响本地栈。
- T03 已验证 Pydantic → JSON Schema → TypeScript 生成链；Pydantic 与 Ajv 共用非法样例并一致拒绝，生成 artifacts 有双端防漂移检查。
- T04 已在真实 PostgreSQL 测试栈完成 Alembic upgrade/downgrade/upgrade；幂等中间件端到端验证同请求只执行一次、冲突请求返回 409。
- T05 已固定 `orbit-wars-2p-v1` 与默认 500 步/6.0 舰队速度/4.0 彗星速度；固定 seed 的 reset、原始动作往返、逐步 state hash、2P 限制和 Apache-2.0 来源审计均有自动化测试，全仓 Python 测试增至 41 项。
- T06 已固化固定 seed 55 步、真实历史 replay 75 步和 v69 对 exp34 103 步三类命令流；每步双跑并比较 planets、fleets、reward、done、结束步和 state hash，差异信息定位到 case/step/field。另移植 4 项上游回归，浮点 hash 明确按 9 位小数/`1e-9` 容差跨平台归一化，全仓 Python 测试增至 52 项。
- T07 已实现 Worker 侧版本化引擎适配、严格比赛状态机、脚本动作提供器、命令 hash 与逐步权威 frame 记录；真实 500 帧空动作局双跑 hash 一致，非法转换、玩家 forfeit、平台 failed 和非法动作归因均有测试，全仓 Python 测试增至 59 项。
- T08 已建立 Orbit Language editorial/tactical 双密度 token、轨道母题、Aurora/Cinder 颜色+形状+纹理双编码、响应式组件基元和原创资产清单；`/design-preview` 覆盖品牌与 HUD 场景，Next 生产构建通过。Browser 实测 1280px/390px 无横向溢出，`motion=reduced` 下 orbit/scan 动画均为 none 且倒计时与控制标签完整。
- T09 已实现 OIDC 账号映射与舰队创建/读取/编辑 API、数据库单舰队唯一约束、随机公开档案 ID、字段规范化和原创外观引用检查；非所有者私有读写统一返回 404，匿名公开投影不包含 UUID、OIDC subject 或当前策略内部 ID。定向覆盖 10 项，`pnpm check` 全量通过，Python 测试增至 69 项。
- T10 已实现内容寻址的不可变 ZIP 策略包、根 `manifest.json` 合同、SHA-256 舰队内去重、发布元数据、单向状态机和 ready 当前版本指针；S3 使用条件写与 hash/size 复核，数据库失败会补偿删除，新对象清理失败则保留同内容可重试键。0002 已在真实 PostgreSQL 完成 upgrade/downgrade/upgrade，测试 MinIO 完成首次写入/重复去重/删除 round-trip；`pnpm check` 全量通过，Python 测试增至 83 项。
- T11 已实现版本化 JSONL runner、导入/单步墙钟超时、动作与请求边界、用户 stdout/stderr 截断和安全错误分类；Docker 调用固定非 root UID、无网络、只读根与策略挂载、tmpfs、cap drop、no-new-privileges、CPU/内存/PID/file limits，基础镜像固定 digest。真实容器验收通过网络/宿主路径/环境凭据/根与包写入、cgroup 内存和 PID、fork 压力、超量日志及死循环终止；`pnpm check` 全量通过，Python 常规测试为 95 passed/3 容器测试默认 skipped，容器模式额外 3 passed。
- T12 已实现 ZIP 路径/链接/文件数/解压量/压缩比安全检查、隔离导入、契约动作、资源时限和固定 seed 24 步验证局，并将稳定安全分类写入 ready/rejected 报告；新增基础、训练和带 ObservationV1 适配层的原始 producer v69 专家包及来源 hash。stdlib 与独立 Torch 2.5.1 固定依赖镜像均通过真实 Docker 固定局，新舰队事务内绑定 ready 基础版本；0003 PostgreSQL 迁移往返通过，`pnpm check` 为 106 passed/5 Docker 测试默认 skipped，Docker 模式相关 15 项全部通过。
- T13 已实现单舰队 scoped Agent Key 的一次性明文、HMAC-SHA256 摘要存储、last-used 审计、并行轮换与幂等撤销；Agent API 提供 fleet/versions/opponents/matches，并支持 base64 ZIP 发布后同步走 T12 验证。scope 403、撤销/错误 key 401、滑动窗口 429、内容去重和 ready 发布均有端到端测试，外部 AI 最小发布示例与安全错误码记录在 `docs/agent-guide.md`；`pnpm check` 全量通过，Python 测试增至 110 passed/5 Docker 测试默认 skipped。
- T14 已实现站内与 Agent API 双入口的 2P 训练模拟编排，固定 ruleset、地图、服务端 seed、双方舰队与不可变 ready 策略版本；支持三种内置 Bot 和公开舰队对手。业务请求指纹保证重试幂等并拒绝同 key 异载荷，舰队与 Agent Key 分维度限流；完成/失败状态和结果可查询，测试确认不产生 rating event。0004 已完成 SQLite upgrade/downgrade/upgrade，API 定向测试 50 passed/2 Docker skipped。
- T15 已在 Worker 增加 Human/Agent 统一 Adapter、默认 3 秒单调时钟和私密双提交 TurnCoordinator；CommandBatch 同步校验 match/step/slot、最多 6 条命令、源星所有权及同源聚合库存，未提交为空动作。迟到、重放、错误 step、越权、超预算、重复提交和幂等冲突均有稳定错误码，定向测试 8 passed，Python strict typecheck 通过。
- T16 已实现训练/排位统一创建 API、服务端随机槽位与 seed、控制方式及 ready 策略版本锁定、Redis 幂等队列和 5 分钟 match/slot/fleet 绑定 JWT 票据；业务请求指纹防重复并拒绝异载荷重试，参与者外不可读取。定向 API 测试覆盖票据越界、队列去重和不可变归因。
- T17 已补齐 turn accepted/closed 共享契约，WebSocket 使用短期票据鉴权并发送 slot 视角 snapshot；命令进入私有 Redis Stream，权威事件通过事件 Stream 广播，resync 对乱序/重复历史按 step 排序去重。双槽位 snapshot、私密命令、accepted 和断线续接均有网关测试，契约生成与双端测试通过。
- T18 已在 `/battle/demo` 建立 PixiJS 权威战场与 DOM HUD，支持己方源星选择、指针/滑杆瞄准、库存约束、最多六条待提交命令、空动作、服务器状态回显、倒计时和完整键盘路径；包含 30 FPS 低性能开关及 reduced-motion 样式。Web lint/typecheck/3 tests/Next production build 全通过；浏览器实测 1280×720 与 390×844 均有一个 Pixi canvas、无横向溢出，真实点击可生成 P-0 待提交命令且控制台零错误。
- T19 已实现 Worker 每槽位独立 Local/Docker AgentProcess、step/slot scoped requestId、1 秒 sandbox 硬限、软预算与累计 overage、日志截断、崩溃及连续三次超时归因；Agent-v-Agent 逐逻辑 step 加速运行且不等待墙钟，Human-v-Agent 保持双方私有视角。两种组合均完成 500 步端到端局，异常稳定判负，Worker 21 tests 与 strict typecheck 全通过。
- T20 已实现幂等 command journal、每 20 步 state-hash checkpoint、seed+命令流确定性恢复、hash 不符即平台 failed 边界、连续 10 次人类断线判负及可重试 finalizing 协调器。故障测试覆盖短暂存储重试、Worker 在第 37 步重启后恢复至第 80 步与无故障 hash 完全一致、损坏 checkpoint、对象存储首传失败及重复终局不重复结算；定向 5 tests 与 strict typecheck 通过。
- T21 已实现逐帧 gzip JSONL 流式 writer，仅保留上一帧，首帧及每 20 步写完整 checkpoint、其余写 delta，并同记录原始双方命令；终局生成 SHA-256、schema/frame/checkpoint 元数据并支持相同工件安全重传。101 帧 fixture 验证 6 个 checkpoint，公开白名单确认不含 key、ticket、源码或 stack。
- T22 已实现纯派生回放分析器，可重建 checkpoint+delta，稳定产出占领、母星易手、最大出击、产能/兵力领先反转、淘汰、超时/断线和终局事件，并计算星球、产能、驻守、在途与控制率曲线；胜因仅引用这些数值。fixture 覆盖 7 类事件、双跑结果相同且原始 records 未被修改。
- T23 已扩展 replay metadata/analysis 持久化与 0005 迁移，匿名 API 提供元数据、checksum 校验流、S3 短期 URL 回退和按 20 步 checkpoint 分段；私有回放稳定 404。`/replay/[publicId]` 播放器支持播放/暂停、0.5–4×、逐步、拖动、事件跳转、双方控制标签和排名变化，checkpoint 重建单测及 Web lint/typecheck/4 tests/生产构建均通过。
- T24 已实现 fleet_id 唯一的保守 rating、段位投影与 match_id 唯一结算事件；human/agent 只作参与归因，重复 finalizing 返回同一事件，training/failed/无唯一胜者不计分。
- T25 已实现统一匹配池、分差与 24 小时重复对手惩罚、定向挑战限制、可审计原因及 1/0.5/0.25/0 计分倍率；站内和 scoped Agent API 均支持幂等挑战，零倍率不改变 mu、sigma 或展示分。
- T26 已实现匿名今日/本周/历史统一榜单及 controller 标签筛选、公开舰队档案、版本谱系、近期 rating 变化和代表回放；测试确认筛选后仍只有每舰队一行 rating，历史比赛固定引用当时 controller 与 strategy version，且响应不泄露 manifest/object key。
- T27 已将首页升级为原创轨道母题与时尚编辑式构图，首屏直接说明 Human/Agent 双控制与唯一排名；`/start` 三步流程完成舰队身份、基础版本与首场手动训练/Agent 模拟选择，并直达战术台或指挥中心。
- T28 已实现 `/command` 统一排名、近期标签、策略历史、当前版本指针、Key 生成/一次显示/撤销和 Agent Guide；Owner API 新增安全 Key 列表与 ready 历史版本切换，响应不含 secret digest、manifest、源码或内部日志。
- T29 已实现 `/arena` 控制者与训练/排位选择、排位不可撤销确认、队列状态、`/leaderboard` 单榜筛选和 `/fleet/[publicId]` 编辑式公开档案；Web lint/typecheck/7 tests/Next production build 通过。
- T30 已贯通 API `requestId` 与 Worker `matchId/step/sandboxId` 安全结构化事件，建立 HTTP、队列、回合、沙箱、回放、结算、重连和 determinism 指标允许列表；递归脱敏覆盖 Bearer、Agent Key、会话、ticket 与源码，高优先级 determinism/重复结算/沙箱逃逸告警及 7–90 天数据保留和事故响应手册均已测试/记录。
- T31 已在单个全新 SQLite 数据库中自动串行走通“创建→Human 训练”“创建→scoped Agent 发布 ready 版本→模拟”“Agent-v-Human 排位→唯一 rating 结算→checksummed 公共回放→匿名档案”；验收映射同时引用既有幂等、权限、协议、恢复、对象存储失败和基础设施故障测试。
- T32 已将 Pixi 战场从每次瞄准重建实例改为常驻实例重绘，并在 ticker 固定标准 60 FPS/低性能 30 FPS；自动预算测试覆盖 16.67/33.33ms p95、每次 replay seek 最多 20 帧、键盘/aria-live/reduced-motion。原创性审计逐项排除 Star Wars 可识别元素、AgenTank 页面复刻与具体时尚品牌资产；生产配置、发布/事故手册齐备。SQLite release drill 和真实 PostgreSQL 0001→0006 upgrade/downgrade/upgrade、custom-format 备份到新库恢复 marker 均成功，三项基础设施健康，真实 stdlib/Torch Sandbox 15 tests 通过；`pnpm check` 最终为 JS 26 tests、Python 150 passed/5 skipped。

## 备注

- 参考产品是 AgenTank，借鉴的是 Agent-first、版本、排位和回放闭环，不复制其品牌、坦克玩法或素材。
- 现有 orbit-wars 仓库提供了星球运动、舰队发射、2P/4P Agent、固定种子评测和回放诊断基础。
- 第一阶段建议只做 2P，以保证规则、手动操作、回放和统一排行榜口径清晰；4P 后置。
- 视觉方向已确认可带有星际战争类型特征，但必须使用原创品牌、舰船、阵营、字体、声音和界面系统。
- 布局可吸收高端时尚杂志/品牌型录的构图语言，并被允许大胆创新，但不复制具体站点。
- 技术架构采用 Next.js Web + Python API/Match Worker + 隔离 Agent Sandbox。
- 规则引擎从 Apache-2.0 Kaggle Environment 中固定提取，网站 ruleset 不跟随上游静默升级。
- 人类实时战采用每原始引擎步 3 秒同步指令窗口；Agent-vs-Agent 可加速墙钟时间但不改变逻辑步。
- 120 份本地 2P 回放样本：中位 178 步，75 分位 213 步，最大 500 步。
- 实现任务已分为五个波次：可复现底座、Agent 与模拟、实时统一对战、回放与竞技产品、公开上线。
- 本地 Python 3.11 的 libedit/readline 与 pytest 8.4+ 启动捕获存在崩溃，开发依赖暂固定 pytest 7.4.4；CI 使用相同锁定版本。
- PostgreSQL 本地镜像固定为 `postgres:16-alpine`；当前任务不依赖更高版本特性，后续升级须通过迁移和恢复验证。
- 固定规则内核来源为 Kaggle Environments 1.30.1、commit `462efa26dd3d11018cde2b9e9ce9245b91cef471`；生产包不导入 Kaggle runtime，后续规则行为变化必须新增 `ruleset_id`。
- Golden fixtures 生成平台记录为 Darwin arm64 / Python 3.11.5；CI 不依赖 Kaggle 包，只消费已审计动作流与字段指纹。历史样本使用无中途 Agent ERROR 的 `79969550`，避免把控制器故障状态混入纯规则引擎回归。
- 原创视觉基线只使用项目内 CSS 几何、排版和程序化纹理，来源登记在 `apps/web/public/assets/sources.json`；未引入影视 Logo、角色、可识别舰船、配乐、AgenTank 资产或具体时尚品牌素材。

## 疑问

- 当前无阻塞疑问。
- 3 秒回合窗口、连续 10 回合断线判负等默认值在任务实施后的体验测试中定标，但不改变协议和架构。
