import { describe, expect, it } from "vitest";

import { canQueue, canRevealAgentSecret, filterByControl } from "./product";
import { resolveHumanPlayEnabled } from "./features";

describe("product guardrails", () => {
  it("requires explicit confirmation only for ranked matches", () => {
    expect(canQueue("training", false)).toBe(true);
    expect(canQueue("ranked", false)).toBe(false);
    expect(canQueue("ranked", true)).toBe(true);
  });

  it("uses controller values as filters over one list", () => {
    const entries = [
      { id: 1, controlTags: "HUMAN · AGENT" },
      { id: 2, controlTags: "HUMAN" },
    ];
    expect(filterByControl(entries, "all")).toHaveLength(2);
    expect(filterByControl(entries, "agent")).toEqual([entries[0]]);
  });

  it("reveals an Agent secret only in the issuance response", () => {
    expect(canRevealAgentSecret(true)).toBe(true);
    expect(canRevealAgentSecret(false)).toBe(false);
  });

  it("keeps manual play closed unless the explicit feature flag is true", () => {
    expect(resolveHumanPlayEnabled(undefined)).toBe(false);
    expect(resolveHumanPlayEnabled("false")).toBe(false);
    expect(resolveHumanPlayEnabled("true")).toBe(true);
  });
});
