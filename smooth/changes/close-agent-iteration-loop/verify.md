# 验证

## 验收结论

**通过。** 状态感知主行动、首页真实回放预览、最近公开对局和回放 Agent 分析交接均已实现，未发现阻塞发布的问题。

## 浏览器验收

- `/zh` 桌面：首屏加载真实 `RANKED` 对局，BattleStage 实测为 `446 × 446`，页面宽度与 scrollWidth 同为 `1178`；第三幕展示 3 场最近公开对局。
- `/en` 桌面：主标题、状态行动、真实回放摘要和三场最近对局均为英文；页面无横向溢出。
- `/en` 窄屏：视口宽度 `390`，document scrollWidth `390`；主标题、状态行动和真实战场构图可读。
- 回放页：compact 与 102/102 权威帧加载完成；Agent 交接区桌面双栏、窄屏单栏均可用。
- 复制验收：`Hand to Agent` 点击后显示 `Copied`；内置浏览器 Clipboard promise 悬空场景已通过 800ms 超时 + legacy copy 降级修复。
- 回放与首页验收后控制台 warning/error 数量为 0。

## 生产构建

- `pnpm --filter @orbit-wars/web build`：通过。
- `pnpm --filter @orbit-wars/web start --port 3003`：通过，生产服务已在 `http://localhost:3003` 运行。


## 自动化检查记录 - 2026-07-18T14:04:04.925Z

| 检查 | 结果 | 命令 |
|---|---|---|
| smooth-artifacts | pass | `（内置）` |
| lint | pass | `pnpm run lint` |
| typecheck | pass | `pnpm run typecheck` |
| test | pass | `pnpm run test` |

### smooth-artifacts

校验 Smooth 变更产物结构

结果：**pass**（2ms）

```text
变更产物结构有效。
```

### lint

检测到 package script：lint

结果：**pass**（16973ms）

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

结果：**pass**（8507ms）

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

结果：**pass**（39219ms）

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
packages/design-tokens test:    Start at  22:03:29
packages/design-tokens test:    Duration  1.08s (transform 136ms, setup 0ms, import 208ms, tests 27ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  22:03:29
packages/contracts test:    Duration  1.77s (transform 525ms, setup 0ms, import 1.78s, tests 42ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  12 passed (12)
apps/web test:       Tests  47 passed (47)
apps/web test:    Start at  22:03:32
apps/web test:    Duration  3.48s (transform 2.83s, setup 0ms, import 4.07s, tests 429ms, environment 20ms)
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
165 passed, 5 skipped, 1 warning in 26.76s
```
