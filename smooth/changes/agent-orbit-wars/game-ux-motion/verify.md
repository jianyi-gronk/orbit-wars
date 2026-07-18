# 验收记录

## 自动检查

- `pnpm check` 通过。
- JavaScript/TypeScript：lint、typecheck、Web 24 项测试、contracts 12 项测试、design tokens 4 项测试全部通过。
- Python：ruff、mypy、162 项测试通过，5 项按环境条件跳过。
- `pnpm --filter @orbit-wars/web build` 通过，Next.js 生产构建完成。

## 浏览器证据

- 1280px 中文首页无横向溢出；四幕分别呈现战区简报、三步作战循环、真实对手网络和 Agent 协议。
- 滚轮向下：场景索引 `0 → 1`，容器滚动 `0 → 720`；滚轮向上恢复 `1 → 0`。
- 键盘 PageDown：`0 → 1`；Home：`1 → 0`。
- 场景指示器点击：`0 → 2`，点击瞬间存在 1 个 interaction pulse。
- 任务菜单：唯一 summary 可点击，打开后有 5 个次级入口，并触发 1 个 interaction pulse。
- 英文首页 `lang=en`，四幕英文内容完整，页面宽度 1280/1280。
- 390×844 中文首页四幕均可直接到达，各幕页面宽度均为 390/390；移动端标题、卡片、协议控制台与 CTA 无横向溢出。

## 降级与可访问性

- 场景 rail 提供中英文 aria-label 与当前步骤状态。
- 键盘支持 ArrowUp/Down、PageUp/Down、Home、End。
- reduced motion 时关闭滚轮接管、视差、扫描线、雷达与点击脉冲；原生滚动和直接场景跳转仍可用。

## 自动化检查记录 - 2026-07-18T05:35:42.129Z

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

结果：**pass**（11907ms）

```text
> orbit-wars-platform@0.1.0 lint /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm lint:js && pnpm lint:python


> orbit-wars-platform@0.1.0 lint:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run lint

Scope: 3 of 4 workspace projects
packages/design-tokens lint$ tsc --noEmit
packages/contracts lint$ pnpm check:generated && tsc --noEmit
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

结果：**pass**（7877ms）

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

Success: no issues found in 72 source files
```

### test

检测到 package script：test

结果：**pass**（45563ms）

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
packages/design-tokens test:    Start at  13:34:58
packages/design-tokens test:    Duration  388ms (transform 74ms, setup 0ms, import 108ms, tests 8ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  13:34:58
packages/contracts test:    Duration  826ms (transform 215ms, setup 0ms, import 1.05s, tests 21ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  10 passed (10)
apps/web test:       Tests  24 passed (24)
apps/web test:    Start at  13:35:01
apps/web test:    Duration  2.27s (transform 1.35s, setup 0ms, import 2.25s, tests 210ms, environment 2ms)
apps/web test: Done

> orbit-wars-platform@0.1.0 test:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m pytest

.............................................................ss......... [ 43%]
....................................sss................................. [ 86%]
.......................                                                  [100%]
=============================== warnings summary ===============================
.venv/lib/python3.11/site-packages/fastapi/testclient.py:1
  /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/.venv/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
162 passed, 5 skipped, 1 warning in 31.72s
```
