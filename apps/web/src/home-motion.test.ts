import { describe, expect, it } from "vitest";

import {
  adjacentSceneIndex,
  clampSceneIndex,
  createWheelGestureState,
  HOME_WHEEL_GESTURE_RELEASE_MS,
  HOME_WHEEL_INTENT_THRESHOLD,
  HOME_WHEEL_INTENT_WINDOW_MS,
  reduceWheelGesture,
  sceneState,
} from "./home-motion";

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

  it("does not navigate for a slight wheel movement", () => {
    const result = reduceWheelGesture(createWheelGestureState(), 60, 100);

    expect(result.direction).toBe(0);
    expect(result.state.accumulatedDelta).toBe(60);
    expect(HOME_WHEEL_INTENT_THRESHOLD).toBe(150);
    expect(HOME_WHEEL_INTENT_WINDOW_MS).toBe(420);
    expect(HOME_WHEEL_GESTURE_RELEASE_MS).toBe(180);
  });

  it("accumulates wheel intent before moving one scene", () => {
    const first = reduceWheelGesture(createWheelGestureState(), 70, 100);
    const second = reduceWheelGesture(first.state, 80, 300);

    expect(second.direction).toBe(1);
    expect(second.state.accumulatedDelta).toBe(0);
  });

  it("extends the scene lock across inertial events from one gesture", () => {
    const triggered = reduceWheelGesture(createWheelGestureState(), 180, 100);
    const inertia = reduceWheelGesture(triggered.state, 80, 200);

    expect(triggered.direction).toBe(1);
    expect(inertia.direction).toBe(0);
    expect(inertia.state.lockedUntil).toBe(380);
  });

  it("allows at most one scene change during sustained scrolling", () => {
    const triggered = reduceWheelGesture(createWheelGestureState(), 180, 100);
    const inertia = reduceWheelGesture(triggered.state, 80, 200);
    const sustained = reduceWheelGesture(inertia.state, 180, 300);

    expect(sustained.direction).toBe(0);
    expect(sustained.state.lockedUntil).toBe(480);
  });

  it("accepts a new gesture after a clear pause", () => {
    const triggered = reduceWheelGesture(createWheelGestureState(), 180, 100);
    const inertia = reduceWheelGesture(triggered.state, 80, 200);
    const nextGesture = reduceWheelGesture(inertia.state, -180, 390);

    expect(nextGesture.direction).toBe(-1);
  });
});
