# 验证


## 自动化检查记录 - 2026-07-18T16:56:19.245Z

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

结果：**pass**（9377ms）

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

结果：**pass**（15293ms）

```text
> orbit-wars-platform@0.1.0 typecheck /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm typecheck:js && pnpm typecheck:python


> orbit-wars-platform@0.1.0 typecheck:js /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> pnpm --recursive --if-present run typecheck

Scope: 3 of 4 workspace projects
packages/design-tokens typecheck$ tsc --noEmit
packages/contracts typecheck$ tsc --noEmit
packages/design-tokens typecheck: Done
packages/contracts typecheck: Done
apps/web typecheck$ tsc --noEmit
apps/web typecheck: Done

> orbit-wars-platform@0.1.0 typecheck:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m mypy services/api/orbit_api services/match-worker/orbit_match_worker services/agent-sandbox/orbit_agent_sandbox packages/orbit-engine-py/orbit_engine packages/platform-runtime-py/orbit_runtime packages/contracts/orbit_contracts

Success: no issues found in 75 source files
```

### test

检测到 package script：test

结果：**pass**（18629ms）

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
packages/design-tokens test:    Start at  00:56:02
packages/design-tokens test:    Duration  315ms (transform 102ms, setup 0ms, import 135ms, tests 3ms, environment 0ms)
packages/design-tokens test: Done
packages/contracts test:  Test Files  2 passed (2)
packages/contracts test:       Tests  12 passed (12)
packages/contracts test:    Start at  00:56:02
packages/contracts test:    Duration  497ms (transform 226ms, setup 0ms, import 574ms, tests 18ms, environment 0ms)
packages/contracts test: Done
apps/web test$ vitest run
apps/web test:  RUN  v4.1.10 /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/apps/web
apps/web test:  Test Files  13 passed (13)
apps/web test:       Tests  51 passed (51)
apps/web test:    Start at  00:56:03
apps/web test:    Duration  714ms (transform 631ms, setup 0ms, import 1.24s, tests 169ms, environment 1ms)
apps/web test: Done

> orbit-wars-platform@0.1.0 test:python /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat
> sh scripts/python.sh -m pytest

.................................................................ss..... [ 41%]
...........................................sss.......................... [ 82%]
..............................                                           [100%]
=============================== warnings summary ===============================
.venv/lib/python3.11/site-packages/fastapi/testclient.py:1
  /Users/jianyi-gronk/Documents/Codex/2026-07-17/new-chat/.venv/lib/python3.11/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
169 passed, 5 skipped, 1 warning in 14.21s
```

## 最终生产验证 - 2026-07-19

- `pnpm check`：通过；Web 51 项、Python 169 项通过，5 项环境相关测试跳过。
- `pnpm --filter @orbit-wars/web build`：通过；Next.js 生产构建完成，所有动态路由生成成功。
- 公开榜单：中文真实数据加载成功，积分/胜率/胜场 URL 可切换，战绩包含 W-L-D 与真实胜率。
- 公开历史：中英文胜负、战况强度、双方 rating 与高光均可读；无唯一胜方的旧记录显示为平局。
- 高光深链：从历史页点击 `STEP 009 / 兵力领先变化` 后，回放加载到 STEP 009，时间线值为 9。
- 复制反馈：回放链接显示“已复制”；指挥中心完整接入包显示“接入包已复制”。
- 指挥中心：本地开发身份真实加载“缺 Agent Key”状态；生成 Key 后显示完整接入包与仅 Key 两种动作，撤销后恢复初始状态；英文任务文案同步。
- 视觉：桌面实页截图检查通过；窄屏折叠由响应式 CSS 与质量测试共同保护，历史高光降为单列，指挥中心 NEXT 与榜单列按断点收敛。
- 最终运行态：无开发身份的干净生产构建已重新启动，Web `http://localhost:3003`，API `http://127.0.0.1:8000`。

## 标题垂直节奏回归 - 2026-07-19

- 根因：展示字体在大字号中文场景使用 `0.73～0.88` 行高，字面高度超出行盒，造成上下行字形碰撞。
- 修复：首页主标题与分幕标题提升至 `0.98`，公共页大标题与 display title 提升至 `1`，任务/卡片/错误标题提升至 `1.08`；同时收敛负字距。
- 第四幕：把中英文两条 directive 拆为独立语义 span，桌面和窄屏使用各自字号，避免行高修复后产生意外第三行。
- 自动保护：Web 新增标题行高与移动端覆盖检查，Web 52 项测试通过。
- 全量验证：`pnpm check` 通过，Python 169 项通过、5 项环境相关跳过；Next.js 生产 build 通过。
- 浏览器：逐页检查中英首页四幕、中文历史、英文榜单、英文创建页、中文竞技场和中文回放错误页；生产版本首页与历史页截图复验无碰撞、切字或异常换行。
- 运行态：生产 Web 继续运行于 `http://localhost:3003`，API 继续运行于 `http://127.0.0.1:8000`。
