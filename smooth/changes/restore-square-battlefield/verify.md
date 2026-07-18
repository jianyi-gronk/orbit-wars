# 验证

## 代码审查

- [x] `battlefieldViewport()` 对宽屏和高屏都返回统一 scale、正方形 size 和居中 offset。
- [x] 网格、太阳、星球、舰队、瞄准线全部使用同一 viewport 变换。
- [x] 指针瞄准把 viewport offset 纳入源星坐标，没有保留旧长方形投影。
- [x] replay 桌面与移动端容器都使用 `aspect-ratio: 1`。
- [x] 太阳核心仅占危险半径约 24%，真实 `SUN_RADIUS` 使用独立虚线环表达。
- [x] 太阳使用不规则日冕和不对称耀斑，不再使用十二刻度与多层实心靶心。

## 自动化检查

- [x] `pnpm --filter @orbit-wars/web test` — 10 个测试文件、34 个测试通过。
- [x] `pnpm --filter @orbit-wars/web typecheck`
- [x] `pnpm --filter @orbit-wars/web lint`
- [x] `pnpm --filter @orbit-wars/web build`
- [x] `npx @pureforge/smooth check restore-square-battlefield` — Smooth 产物、全仓 lint 和 typecheck 通过。

## 证据

- `battlefieldViewport(1200, 700)` 返回 700×700、水平偏移 250、scale 7。
- `battlefieldViewport(500, 800)` 返回 500×500、垂直偏移 150、scale 5。
- quality test 锁定 replay CSS 的 `aspect-ratio: 1`。
- 生产构建成功生成全部 Next.js 路由。
- 本地页面与指定 replay compact 同源接口均返回 HTTP 200。

## 手动验证

- [ ] 刷新指定公开回放，确认地图为正方形，太阳为小型恒星核心与独立虚线危险环。

## 自动化检查记录 - 2026-07-18T12:09:44.377Z

| 检查 | 结果 | 命令 |
|---|---|---|
| smooth-artifacts | pass | `（内置）` |
| lint | pass | `pnpm run lint` |
| typecheck | pass | `pnpm run typecheck` |
| test | pass | `pnpm run test` |

### smooth-artifacts

校验 Smooth 变更产物结构

结果：**pass**（9ms）

```text
变更产物结构有效。
```

### lint

检测到 package script：lint

结果：**pass**（21198ms）

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

结果：**pass**（10307ms）

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

结果：**pass**（36772ms）

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
packages/design-tokens test:    Start at  20:09:09
packages/design-tokens test:    Duration  495ms (transform 54ms, setup 0ms, import 86ms, tests 5ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  20:09:09
packages/contracts test:    Duration  746ms (transform 149ms, setup 0ms, import 632ms, tests 21ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  10 passed (10)
apps/web test:       Tests  34 passed (34)
apps/web test:    Start at  20:09:10
apps/web test:    Duration  987ms (transform 446ms, setup 0ms, import 865ms, tests 273ms, environment 2ms)
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
165 passed, 5 skipped, 1 warning in 30.36s
```
