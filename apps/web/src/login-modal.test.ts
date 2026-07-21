import { describe, expect, it } from "vitest";

import { safeLoginReturnTo, withLoginPrompt } from "./login-modal";

describe("login modal navigation", () => {
  it("keeps safe internal return paths", () => {
    expect(safeLoginReturnTo("/zh/start?mode=ranked", "zh")).toBe("/zh/start?mode=ranked");
  });

  it("rejects protocol-relative and missing destinations", () => {
    expect(safeLoginReturnTo("//example.com/steal", "zh")).toBe("/zh");
    expect(safeLoginReturnTo(undefined, "en")).toBe("/en");
  });

  it("adds the modal prompt without dropping query or hash state", () => {
    expect(withLoginPrompt("/en/start?mode=ranked#fleet", "en")).toBe(
      "/en/start?mode=ranked&auth=login#fleet",
    );
  });
});
