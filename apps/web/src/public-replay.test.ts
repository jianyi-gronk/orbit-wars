import { describe, expect, it } from "vitest";

import {
  buildAgentAnalysisBrief,
  matchModeName,
  publicReplayDataUrl,
  replayReasonName,
  type CompactReplay,
} from "./public-replay";

const compact: CompactReplay = {
  publicId: "replay_public",
  matchPublicId: "match_public",
  mapId: "orbit-standard-v1",
  mode: "ranked",
  frameCount: 168,
  result: { winnerSlot: 1, reason: "home_planet_lost", finalStep: 167 },
  participants: [
    { slot: 0, fleetName: "Helix", controllerType: "agent", strategyVersionId: "v1" },
    { slot: 1, fleetName: "Vanta", controllerType: "agent", strategyVersionId: "v2" },
  ],
  ratingChanges: [{ fleetPublicId: "fleet_1", delta: -12.5 }],
  events: [{ step: 120, type: "ship_lead_changed", slot: 1 }],
  facts: ["Slot 1 controlled 36 planets."],
  deepLinks: { artifact: "/raw", segmentTemplate: "/segments/{checkpoint}" },
};

describe("public replay handoff", () => {
  it("builds an absolute public compact URL", () => {
    expect(publicReplayDataUrl("replay_public", "https://orbit.example")).toBe(
      "https://orbit.example/orbit-api/api/public/v1/replays/replay_public/compact",
    );
  });

  it("contains authoritative public context without key material", () => {
    const brief = buildAgentAnalysisBrief({
      locale: "zh",
      compact,
      replayUrl: "https://orbit.example/zh/replay/replay_public",
      dataUrl: publicReplayDataUrl(compact.publicId, "https://orbit.example"),
    });
    expect(brief).toContain("match_public");
    expect(brief).toContain("ship_lead_changed");
    expect(brief).toContain("3 个可验证");
    expect(brief).not.toContain("owk_");
    expect(brief).not.toContain("Agent Key");
  });

  it("localizes authoritative match modes without defaulting unknown values to ranked", () => {
    expect(matchModeName("zh", "ranked")).toBe("排位赛");
    expect(matchModeName("en", "training")).toBe("Training");
    expect(matchModeName("zh", "strategy_simulation")).toBe("策略模拟");
    expect(matchModeName("en", "legacy_mode")).toBe("Unknown mode");
  });

  it("localizes the engine step-limit outcome", () => {
    expect(replayReasonName("zh", "step_limit")).toBe("回合上限");
    expect(replayReasonName("en", "step_limit")).toBe("Turn limit");
  });
});
