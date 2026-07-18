import { describe, expect, it } from "vitest";

import { CONTRACTS_SCHEMA_VERSION } from "../src/index";

describe("contracts package", () => {
  it("exposes an explicit schema version", () => {
    expect(CONTRACTS_SCHEMA_VERSION).toBe(1);
  });
});
