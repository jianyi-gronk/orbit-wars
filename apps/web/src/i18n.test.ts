import { describe, expect, it } from "vitest";

import { errorMessage, localPath, localeFrom, messages, swapLocale } from "./i18n";

describe("localized paths", () => {
  it("preserves business paths while switching language", () => {
    expect(swapLocale("/zh/replay/replay_123", "en")).toBe("/en/replay/replay_123");
    expect(swapLocale("/leaderboard", "en")).toBe("/en/leaderboard");
    expect(localPath("zh", "/fleet/fleet_1")).toBe("/zh/fleet/fleet_1");
  });

  it("uses Chinese as the stable fallback", () => {
    expect(localeFrom("ja")).toBe("zh");
    expect(errorMessage("en", "fleet.not_found")).toContain("fleet");
  });

  it("keeps common navigation and error keys complete in both languages", () => {
    expect(Object.keys(messages.en.nav).sort()).toEqual(Object.keys(messages.zh.nav).sort());
    expect(Object.keys(messages.en.common).sort()).toEqual(Object.keys(messages.zh.common).sort());
    expect(Object.keys(messages.en.errors).sort()).toEqual(Object.keys(messages.zh.errors).sort());
  });
});
