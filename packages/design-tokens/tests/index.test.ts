import { describe, expect, it } from "vitest";

import { DESIGN_SYSTEM_NAME, DENSITY_TOKENS, FACTION_ENCODINGS, MOTION_TOKENS } from "../src/index";

describe("design token package", () => {
  it("has an independent design-system identity", () => {
    expect(DESIGN_SYSTEM_NAME).toBe("Orbit Language");
  });

  it("separates expressive editorial spacing from tactical density", () => {
    expect(DENSITY_TOKENS.editorial.gap).not.toBe(DENSITY_TOKENS.tactical.gap);
    expect(DENSITY_TOKENS.tactical.contentMax).toBe("100%");
  });

  it("dual-encodes factions without relying on color alone", () => {
    expect(FACTION_ENCODINGS.aurora.shape).not.toBe(FACTION_ENCODINGS.cinder.shape);
    expect(FACTION_ENCODINGS.aurora.pattern).not.toBe(FACTION_ENCODINGS.cinder.pattern);
  });

  it("keeps reduced-motion state changes instantaneous", () => {
    expect(Object.values(MOTION_TOKENS.reduced).every((value) => value === "0ms")).toBe(true);
  });
});
