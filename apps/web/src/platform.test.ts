import { describe, expect, it } from "vitest";

import { PLATFORM_NAME } from "./platform";

describe("platform metadata", () => {
  it("has a stable product name", () => {
    expect(PLATFORM_NAME).toBe("Orbit Wars");
  });
});
