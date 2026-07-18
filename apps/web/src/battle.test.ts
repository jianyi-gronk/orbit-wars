import { describe, expect, it } from "vitest";
import {
  formatPlanetLabel,
  initialDraft,
  queueLaunch,
  selectPlanet,
  setAngle,
  setShips,
  type PlanetView,
} from "./battle";

const planets: PlanetView[] = [
  { id: 0, owner: 0, x: 0, y: 0, radius: 2, ships: 10, production: 1 },
  { id: 1, owner: 1, x: 10, y: 10, radius: 2, ships: 8, production: 1 },
];

describe("human tactical command draft", () => {
  it("selects only owned planets and clamps ship count", () => {
    expect(selectPlanet(initialDraft, planets, 0, 1).error).toContain("己方");
    const selected = selectPlanet(initialDraft, planets, 0, 0);
    expect(setShips(selected, planets, 99).ships).toBe(10);
  });

  it("normalizes aim and rejects aggregate over-budget launches", () => {
    let draft = selectPlanet(initialDraft, planets, 0, 0);
    draft = setAngle(setShips(draft, planets, 6), -Math.PI / 2);
    draft = queueLaunch(draft, planets);
    draft = setShips(draft, planets, 5);
    draft = queueLaunch(draft, planets);
    expect(draft.angle).toBeCloseTo(Math.PI * 1.5);
    expect(draft.pending).toHaveLength(1);
    expect(draft.error).toContain("库存");
  });
});

describe("planet labels", () => {
  it("can hide internal ids while preserving the rounded-down ship count", () => {
    expect(formatPlanetLabel(7, 4.9, false)).toBe("4");
    expect(formatPlanetLabel(7, 4.9)).toBe("7 · 4");
  });
});
