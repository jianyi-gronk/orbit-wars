import { describe, expect, it } from "vitest";
import { checkpointForStep, formatRatingDelta, reconstructSegment } from "./replay";

describe("replay checkpoint seek", () => {
  it("reconstructs deltas from the requested checkpoint", () => {
    const frames = reconstructSegment([
      {
        type: "checkpoint",
        frame: { step: 20, stateHash: "a", planets: [[0, 0, 1, 2, 3, 10, 1]] },
      },
      { type: "delta", frame: { step: 21, stateHash: "b" } },
      {
        type: "delta",
        frame: { step: 22, stateHash: "c", planets: [[0, 1, 2, 3, 3, 4, 1]] },
      },
    ]);
    expect(frames.map((frame) => frame.step)).toEqual([20, 21, 22]);
    expect(frames[1].planets[0].owner).toBe(0);
    expect(frames[2].planets[0].owner).toBe(1);
    expect(checkpointForStep(39)).toBe(20);
    expect(checkpointForStep(40)).toBe(40);
  });
});

describe("replay presentation", () => {
  it("formats noisy rating deltas as stable one-decimal labels", () => {
    expect(formatRatingDelta(245.29999999999995)).toBe("+245.3");
    expect(formatRatingDelta(-12.56)).toBe("-12.6");
    expect(formatRatingDelta(0.0001)).toBe("0.0");
    expect(formatRatingDelta()).toBe("—");
  });
});
