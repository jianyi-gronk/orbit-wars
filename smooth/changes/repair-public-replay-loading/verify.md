# 验证

## 代码审查

- [x] 实际代码变更仅涉及回放记录类型、分段重建、错误诊断和对应测试，没有修改比赛模拟或历史数据。
- [x] `checkpoint` 与 `delta` 继续生成权威帧；终局 `result` 记录被忽略且不会复制最后一帧。
- [x] worker 仍先上传压缩工件，再创建 ReplayArtifact 并绑定 Match；公开历史继续通过 ReplayArtifact 关联公开回放。
- [x] 生产错误面板只显示加载阶段与稳定错误类型；完整异常 message 和对象仅保留在开发环境。
- [x] `/orbit-api`、Next rewrite 和 API 客户端保持不变，没有把浏览器直接导航 API 的限制误当成产品根因。

## 浏览器证据

- [x] 指定 ID 的 compact 与 0、20、40、60、80、100、120、140、160 分段全部返回 200。
- [x] 最后分段包含 160–167 帧及一条 `type: result`、无 `frame` 字段的终局记录，复现了旧重建器的 TypeError。
- [x] 修复后 `replay_JzIuAokYL5Ub3yLAYuuzA-8Y` 显示 168/168 帧完整载入，不再出现离线面板。
- [x] 点击播放后权威帧从 STEP 000 推进到 STEP 003，浏览器 error 日志为 0。

## 补充自动化检查

- [x] `pnpm --filter @orbit-wars/web test` — 10 个测试文件、29 个测试通过。
- [x] `pnpm --filter @orbit-wars/web typecheck` — 通过。
- [x] `pnpm --filter @orbit-wars/web build` — Next.js 生产构建和 13 个页面生成通过。
- [x] 指定 replay/API/worker persistence 测试 — 5 个测试通过。

## 手动验证

回放页面属于核心证据链。后续调整 writer 记录类型时，应至少打开一场已结束回放，确认最后一个 checkpoint 完整载入并能推进帧。

## 自动化检查记录 - 2026-07-18T09:52:35.246Z

| 检查 | 结果 | 命令 |
|---|---|---|
| smooth-artifacts | pass | `（内置）` |
| lint | pass | `pnpm run lint` |
| typecheck | pass | `pnpm run typecheck` |
| test | pass | `pnpm run test` |

### smooth-artifacts

校验 Smooth 变更产物结构

结果：**pass**（1ms）

```text
变更产物结构有效。
```

### lint

检测到 package script：lint

结果：**pass**（12688ms）

```text
> orbit-wars-platform@0.1.0 lint /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm lint:js && pnpm lint:python


> orbit-wars-platform@0.1.0 lint:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run lint

Scope: 3 of 4 workspace projects
packages/contracts lint$ pnpm check:generated && tsc --noEmit
packages/design-tokens lint$ tsc --noEmit
packages/contracts lint: > @orbit-wars/contracts@0.1.0 check:generated /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/packages/contracts
packages/contracts lint: > node scripts/generate-types.mjs --check
packages/design-tokens lint: Done
packages/contracts lint: Done
apps/web lint$ eslint .
apps/web lint: Done

> orbit-wars-platform@0.1.0 lint:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m ruff check services packages/orbit-engine-py

All checks passed!
```

### typecheck

检测到 package script：typecheck

结果：**pass**（10607ms）

```text
> orbit-wars-platform@0.1.0 typecheck /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm typecheck:js && pnpm typecheck:python


> orbit-wars-platform@0.1.0 typecheck:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run typecheck

Scope: 3 of 4 workspace projects
packages/contracts typecheck$ tsc --noEmit
packages/design-tokens typecheck$ tsc --noEmit
packages/design-tokens typecheck: Done
packages/contracts typecheck: Done
apps/web typecheck$ tsc --noEmit
apps/web typecheck: Done

> orbit-wars-platform@0.1.0 typecheck:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m mypy services/api/orbit_api services/match-worker/orbit_match_worker services/agent-sandbox/orbit_agent_sandbox packages/orbit-engine-py/orbit_engine packages/platform-runtime-py/orbit_runtime packages/contracts/orbit_contracts

Success: no issues found in 74 source files
```

### test

检测到 package script：test

结果：**pass**（17393ms）

```text
> orbit-wars-platform@0.1.0 test /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm test:js && pnpm test:python


> orbit-wars-platform@0.1.0 test:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run test

Scope: 3 of 4 workspace projects
packages/contracts test$ vitest run
packages/design-tokens test$ vitest run
packages/contracts test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/packages/contracts
packages/design-tokens test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/packages/design-tokens
packages/design-tokens test:  Test Files  1 passed (1)
packages/design-tokens test:       Tests  4 passed (4)
packages/design-tokens test:    Start at  17:52:19
packages/design-tokens test:    Duration  245ms (transform 33ms, setup 0ms, import 50ms, tests 4ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  17:52:19
packages/contracts test:    Duration  413ms (transform 78ms, setup 0ms, import 412ms, tests 12ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  10 passed (10)
apps/web test:       Tests  29 passed (29)
apps/web test:    Start at  17:52:20
apps/web test:    Duration  568ms (transform 250ms, setup 0ms, import 506ms, tests 122ms, environment 1ms)
apps/web test: Done

> orbit-wars-platform@0.1.0 test:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m pytest

.............................................................ss......... [ 42%]
.......................................sss.............................. [ 84%]
..........................                                               [100%]
=============================== warnings summary ===============================
.venv/lib/python3.11/site-packages/fastapi/testclient.py:1
  /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/.venv/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
165 passed, 5 skipped, 1 warning in 13.38s
```
