import { describe, expect, it } from "vitest";

import { pkceChallenge, safeReturnTo } from "./auth";

describe("OIDC helpers", () => {
  it("accepts only local return paths", () => {
    expect(safeReturnTo("/en/command?tab=keys")).toBe("/en/command?tab=keys");
    expect(safeReturnTo("//attacker.example")).toBe("/zh/command");
    expect(safeReturnTo("https://attacker.example")).toBe("/zh/command");
  });

  it("creates the RFC 7636 S256 challenge", () => {
    expect(pkceChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
  });
});
