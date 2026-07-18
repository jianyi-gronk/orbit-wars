import { describe, expect, it } from "vitest";

import { adjacentSceneIndex, clampSceneIndex, sceneState } from "./home-motion";

describe("home scene navigation", () => {
  it("moves only to an adjacent scene and clamps the ends", () => {
    expect(adjacentSceneIndex(1, 120, 4)).toBe(2);
    expect(adjacentSceneIndex(1, -120, 4)).toBe(0);
    expect(adjacentSceneIndex(0, -120, 4)).toBe(0);
    expect(adjacentSceneIndex(3, 120, 4)).toBe(3);
  });

  it("clamps direct scene requests", () => {
    expect(clampSceneIndex(-3, 4)).toBe(0);
    expect(clampSceneIndex(8, 4)).toBe(3);
    expect(clampSceneIndex(2, 4)).toBe(2);
  });

  it("derives transition states from the active scene", () => {
    expect(sceneState(0, 1)).toBe("before");
    expect(sceneState(1, 1)).toBe("active");
    expect(sceneState(2, 1)).toBe("after");
  });
});
