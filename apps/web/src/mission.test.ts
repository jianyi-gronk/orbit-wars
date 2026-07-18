import { describe, expect, it } from "vitest";

import { resolveMissionAction, resolveMissionState } from "./mission";

describe("mission action", () => {
  it.each([
    [{ authenticated: false }, "signed-out"],
    [{ authenticated: true, hasFleet: false }, "needs-fleet"],
    [
      { authenticated: true, hasFleet: true, hasActiveAgentKey: false },
      "needs-agent",
    ],
    [
      {
        authenticated: true,
        hasFleet: true,
        hasActiveAgentKey: true,
        currentStrategyStatus: "draft",
      },
      "needs-strategy",
    ],
    [
      {
        authenticated: true,
        hasFleet: true,
        hasActiveAgentKey: true,
        currentStrategyStatus: "ready",
      },
      "battle-ready",
    ],
    [{ authenticated: true, incomplete: true }, "continue"],
  ] as const)("resolves %o as %s", (snapshot, expected) => {
    expect(resolveMissionState(snapshot)).toBe(expected);
  });

  it("localizes labels and routes signed-out users through login", () => {
    expect(resolveMissionAction("zh", { authenticated: false })).toEqual({
      state: "signed-out",
      href: "/auth/login?returnTo=%2Fzh%2Fstart",
      label: "开始游戏",
    });
    expect(
      resolveMissionAction("en", {
        authenticated: true,
        hasFleet: true,
        hasActiveAgentKey: true,
        currentStrategyStatus: "ready",
      }),
    ).toEqual({ state: "battle-ready", href: "/en/arena", label: "Play now" });
  });
});
