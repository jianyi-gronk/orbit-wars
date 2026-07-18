import { describe, expect, it } from "vitest";

import { competitiveRankLabel, competitiveRankPoints } from "./rating";

describe("competitive rank localization", () => {
  it("renders the same protocol rank in Chinese and English", () => {
    const rank = { tier: "gold", division: "III", points: 25 } as const;

    expect(competitiveRankLabel("zh", rank)).toBe("黄金 III");
    expect(competitiveRankPoints("zh", rank)).toBe("25 分");
    expect(competitiveRankLabel("en", rank)).toBe("Gold III");
    expect(competitiveRankPoints("en", rank)).toBe("25 pts");
  });

  it("omits a division for master rank", () => {
    const rank = { tier: "master", division: null, points: 42.5 } as const;

    expect(competitiveRankLabel("zh", rank)).toBe("大师");
    expect(competitiveRankPoints("en", rank)).toBe("42.5 pts");
  });
});
