# 验证记录

日期：2026-07-19

结论：通过。站内策略实验室、无 Agent Key 开战与 DeepSeek 免费额度基础能力满足本阶段验收标准。

## 自动化证据

- `pnpm check` 通过：format、lint、JavaScript/Python typecheck 与全量测试均成功。
- JavaScript 测试通过：Web 60 项、Design 4 项、Contracts 12 项。
- Python 测试通过：176 项通过、5 项跳过；仅保留一条既有 Starlette deprecation warning。
- Web 在本地 API 环境及 `NEXT_PUBLIC_ENABLE_HUMAN_PLAY=false` 下完成 production build。
- 临时 SQLite 完成 `0001 → 0008 → 0007 → 0008` 升降级验证；本地 PostgreSQL 已升级至 `0008` head。
- API 测试覆盖 owner 隔离、revision 冲突、确定性策略包、候选模拟不改 current/rating、发布门禁、AI 明确同意、额度原子扣减、失败不扣和预算限制。

## 浏览器证据

- 中文、英文桌面与窄屏页面无横向溢出、无缺失翻译、无控制台错误。
- 首页以“策略实验室 → 训练 → 回放 → 继续优化”为主路径；小幅滚轮操作只推进一个场景。
- 创建/开战路径不要求 Agent Key，同时保留外部 Agent 接入口。
- 草稿保存、模板重置和 revision 更新成功。
- 未配置 DeepSeek Key 时显示可恢复的降级提示，余额仍为 30，用户可继续手动编辑和模拟。
- 候选模拟成功创建训练赛 `match_AP7omW3XrDOXBv3vxaQDXRD5`，返回验证 hash 并开启发布门禁；验收未执行发布，因此没有改变当前策略版本。
- 修复策略实验室激活态按钮文字对比度，hover/active 文案保持可见。

## 待产品确认

- Kaggle 模板在站内可编辑与再分发时采用的最终许可证说明。
- 赠送额度用尽后的付费、充值或 BYOK 路径。本阶段只实现赠送额度与安全预算边界。
