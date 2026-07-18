import { describe, expect, it } from "vitest";
import {
  BATTLEFIELD_SIZE,
  SUN_CENTER,
  SUN_RADIUS,
  aimAtPoint,
  availableShips,
  battlefieldViewport,
  fleetDirection,
  formatPlanetLabel,
  initialDraft,
  queueLaunch,
  removeQueuedLaunch,
  selectPlanet,
  setAngle,
  setShipRatio,
  setShips,
  updateQueuedLaunch,
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
    draft = { ...draft, ships: 5 };
    draft = queueLaunch(draft, planets);
    expect(draft.angle).toBeCloseTo(Math.PI * 1.5);
    expect(draft.pending).toHaveLength(1);
    expect(draft.error).toContain("库存");
  });

  it("aims at map points and offers quick force ratios from unqueued inventory", () => {
    let draft = selectPlanet(initialDraft, planets, 0, 0);
    draft = aimAtPoint(draft, planets, 0, 10);
    expect(draft.angle).toBeCloseTo(Math.PI / 2);
    draft = setShipRatio(draft, planets, 0.5);
    expect(draft.ships).toBe(5);
    draft = queueLaunch(draft, planets);
    expect(availableShips(draft, planets, 0)).toBe(5);
    expect(setShipRatio(draft, planets, 1).ships).toBe(5);
  });

  it("edits and removes queued launches without exceeding planet inventory", () => {
    let draft = selectPlanet(initialDraft, planets, 0, 0);
    draft = queueLaunch(setShips(draft, planets, 4), planets);
    draft = queueLaunch(setShips(draft, planets, 3), planets);
    draft = updateQueuedLaunch(draft, planets, 0, 9);
    expect(draft.pending.map((command) => command.ships)).toEqual([7, 3]);
    draft = removeQueuedLaunch(draft, 1);
    expect(draft.pending).toHaveLength(1);
    expect(availableShips(draft, planets, 0)).toBe(3);
  });
});

describe("planet labels", () => {
  it("can hide internal ids while preserving the rounded-down ship count", () => {
    expect(formatPlanetLabel(7, 4.9, false)).toBe("4");
    expect(formatPlanetLabel(7, 4.9)).toBe("7 · 4");
  });
});

describe("fleet trajectories", () => {
  it("derives the authoritative travel direction from the fleet angle", () => {
    expect(fleetDirection(0)).toEqual({ x: 1, y: 0 });
    expect(fleetDirection(Math.PI / 2).x).toBeCloseTo(0);
    expect(fleetDirection(Math.PI / 2).y).toBeCloseTo(1);
  });
});

describe("central sun rules", () => {
  it("matches the pinned engine collision geometry", () => {
    expect(BATTLEFIELD_SIZE).toBe(100);
    expect(SUN_CENTER).toBe(50);
    expect(SUN_RADIUS).toBe(10);
  });
});

describe("square battlefield viewport", () => {
  it("centers a square board inside wide and tall containers", () => {
    expect(battlefieldViewport(1200, 700)).toEqual({
      size: 700,
      scale: 7,
      offsetX: 250,
      offsetY: 0,
    });
    expect(battlefieldViewport(500, 800)).toEqual({
      size: 500,
      scale: 5,
      offsetX: 0,
      offsetY: 150,
    });
  });
});
