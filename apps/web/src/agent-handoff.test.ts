import { describe, expect, it } from "vitest";

import { buildAgentHandoffBundle, resolveCommandMission } from "./agent-handoff";

describe("Command Center Agent handoff", () => {
  it("resolves the next safe mission in priority order", () => {
    expect(
      resolveCommandMission({ secret: "once", hasActiveKey: false, currentStrategyStatus: null }),
    ).toBe("copy-handoff");
    expect(
      resolveCommandMission({ secret: null, hasActiveKey: false, currentStrategyStatus: "ready" }),
    ).toBe("needs-agent-key");
    expect(
      resolveCommandMission({ secret: null, hasActiveKey: true, currentStrategyStatus: "failed" }),
    ).toBe("needs-ready-strategy");
    expect(
      resolveCommandMission({ secret: null, hasActiveKey: true, currentStrategyStatus: "ready" }),
    ).toBe("battle-ready");
  });

  it("builds a complete one-time bundle without inventing or transforming the secret", () => {
    const secret = "owk_once_only_123";
    const bundle = buildAgentHandoffBundle({
      locale: "en",
      key: secret,
      fleetId: "fleet_public",
      apiBaseUrl: "https://orbit.test/orbit-api/api/agent/v1",
      guideUrl: "https://orbit.test/en/agent-guide",
    });

    expect(bundle).toContain("API Base: https://orbit.test/orbit-api/api/agent/v1");
    expect(bundle).toContain("Guide: https://orbit.test/en/agent-guide");
    expect(bundle).toContain("Fleet ID: fleet_public");
    expect(bundle.match(new RegExp(secret, "g"))).toHaveLength(1);
    expect(bundle).toContain("never save the key in logs, chat, or the repository");
    expect(bundle).not.toContain("localStorage");
  });
});
