# 验证

## 代码审查

- [x] ReplayPlayer 仅通过 `showPlanetIds={false}` 改变回放标签，不修改 replay schema 或历史工件。
- [x] `BattleStage` 的默认值仍为显示 ID，既有实时战场调用保持兼容。
- [x] 隐藏 ID 模式使用 `anchor.set(0.5)` 与星球坐标，将兵力数字水平、垂直居中。
- [x] 星球 ID 仍用于 Pixi 点击选择、选中态查找和帧数据身份关联。

## 自动化检查

- [x] `pnpm --filter @orbit-wars/web typecheck`
- [x] `pnpm --filter @orbit-wars/web lint`
- [x] `pnpm --filter @orbit-wars/web test` — 10 个测试文件、30 个测试通过。
- [x] `pnpm --filter @orbit-wars/web build`
- [x] `npx @pureforge/smooth check refine-replay-planet-labels` — Smooth 产物、全仓 lint 和 typecheck 通过。
- [x] `git diff --check 80a8138..HEAD`（修正文档 EOF 后复查）

## 证据

- `formatPlanetLabel(7, 4.9, false)` 返回 `"4"`，证明回放模式不包含 ID 或分隔点，并保持兵力向下取整。
- `ReplayPlayer` 显式传入 `showPlanetIds={false}`；其他调用未传入，使用兼容默认值。
- Pixi 文本在隐藏 ID 模式下锚点为 `(0.5, 0.5)`，位置与星球中心 `(x, y)` 相同。
- 本地 API 与 Web 服务分别恢复在 `8000` 和 `3003`。
- 页面和指定 replay compact 经本地同源链路请求均返回 HTTP 200。

## 手动验证

- [ ] 刷新现有公开回放标签页，确认星球内部只显示兵力数字。自动刷新被浏览器的本地 URL 安全策略拒绝，因此没有绕过策略代替视觉确认。

## 自动化检查记录 - 2026-07-18T10:59:52.496Z

| 检查 | 结果 | 命令 |
|---|---|---|
| smooth-artifacts | pass | `（内置）` |
| lint | pass | `pnpm run lint` |
| typecheck | pass | `pnpm run typecheck` |
| test | pass | `pnpm run test` |

### smooth-artifacts

校验 Smooth 变更产物结构

结果：**pass**（0ms）

```text
变更产物结构有效。
```

### lint

检测到 package script：lint

结果：**pass**（8296ms）

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

结果：**pass**（4443ms）

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

结果：**pass**（20569ms）

```text
> orbit-wars-platform@0.1.0 test /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm test:js && pnpm test:python


> orbit-wars-platform@0.1.0 test:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run test

Scope: 3 of 4 workspace projects
packages/design-tokens test$ vitest run
packages/contracts test$ vitest run
packages/design-tokens test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/packages/design-tokens
packages/contracts test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/packages/contracts
packages/design-tokens test:  Test Files  1 passed (1)
packages/design-tokens test:       Tests  4 passed (4)
packages/design-tokens test:    Start at  18:59:34
packages/design-tokens test:    Duration  290ms (transform 61ms, setup 0ms, import 91ms, tests 6ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  18:59:34
packages/contracts test:    Duration  585ms (transform 144ms, setup 0ms, import 714ms, tests 17ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  10 passed (10)
apps/web test:       Tests  30 passed (30)
apps/web test:    Start at  18:59:35
apps/web test:    Duration  1.29s (transform 906ms, setup 0ms, import 1.60s, tests 237ms, environment 1ms)
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
165 passed, 5 skipped, 1 warning in 14.53s
```
