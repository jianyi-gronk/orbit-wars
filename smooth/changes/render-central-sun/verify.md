# 验证

## 代码审查

- [x] 前端 `BATTLEFIELD_SIZE = 100`、`SUN_CENTER = 50`、`SUN_RADIUS = 10` 与 pinned kernel 一致。
- [x] 太阳由固定规则常量绘制，不修改 replay schema 或引擎状态。
- [x] 图层顺序为网格、太阳、星球、舰队，太阳不会遮挡兵力和舰标。
- [x] 太阳完整碰撞半径有明确边界，内部核心与外部辉光只用于视觉识别。

## 自动化检查

- [x] `pnpm --filter @orbit-wars/web test` — 10 个测试文件、33 个测试通过。
- [x] `pnpm --filter @orbit-wars/web typecheck`
- [x] `pnpm --filter @orbit-wars/web lint`
- [x] `pnpm --filter @orbit-wars/web build`
- [x] `npx @pureforge/smooth check render-central-sun` — Smooth 产物、全仓 lint 和 typecheck 通过。

## 证据

- 单元测试锁定战场尺寸、中心坐标和太阳碰撞半径。
- 生产构建成功生成全部 Next.js 路由。
- 本地生产 Web 已在 3003 重新启动。
- 页面和指定 replay compact 同源接口均返回 HTTP 200。

## 手动验证

- [ ] 刷新当前公开回放，确认中心太阳、发光核心、十二道短射线及碰撞边界清晰可见。

## 自动化检查记录 - 2026-07-18T11:52:26.685Z

| 检查 | 结果 | 命令 |
|---|---|---|
| smooth-artifacts | pass | `（内置）` |
| lint | pass | `pnpm run lint` |
| typecheck | pass | `pnpm run typecheck` |
| test | pass | `pnpm run test` |

### smooth-artifacts

校验 Smooth 变更产物结构

结果：**pass**（79ms）

```text
变更产物结构有效。
```

### lint

检测到 package script：lint

结果：**pass**（31172ms）

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

结果：**pass**（10650ms）

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

结果：**pass**（55317ms）

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
packages/design-tokens test:    Start at  19:51:36
packages/design-tokens test:    Duration  982ms (transform 90ms, setup 0ms, import 151ms, tests 10ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  19:51:36
packages/contracts test:    Duration  1.60s (transform 339ms, setup 0ms, import 1.47s, tests 49ms, environment 1ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  10 passed (10)
apps/web test:       Tests  33 passed (33)
apps/web test:    Start at  19:51:39
apps/web test:    Duration  3.33s (transform 2.74s, setup 0ms, import 4.44s, tests 588ms, environment 3ms)
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
165 passed, 5 skipped, 1 warning in 41.53s
```
