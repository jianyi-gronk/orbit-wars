export type SceneState = "before" | "active" | "after";

export type WheelGestureState = {
  accumulatedDelta: number;
  lastEventAt: number;
  lockedUntil: number;
};

export type WheelGestureResult = {
  direction: -1 | 0 | 1;
  state: WheelGestureState;
};

export const HOME_WHEEL_INTENT_THRESHOLD = 150;
export const HOME_WHEEL_COOLDOWN_MS = 420;

export function createWheelGestureState(): WheelGestureState {
  return {
    accumulatedDelta: 0,
    lastEventAt: Number.NEGATIVE_INFINITY,
    lockedUntil: 0,
  };
}

export function reduceWheelGesture(
  state: WheelGestureState,
  deltaY: number,
  now: number,
  threshold = HOME_WHEEL_INTENT_THRESHOLD,
  cooldownMs = HOME_WHEEL_COOLDOWN_MS,
): WheelGestureResult {
  if (!Number.isFinite(deltaY) || deltaY === 0 || !Number.isFinite(now)) {
    return { direction: 0, state };
  }

  if (now < state.lockedUntil) {
    return {
      direction: 0,
      state: {
        accumulatedDelta: 0,
        lastEventAt: now,
        lockedUntil: state.lockedUntil,
      },
    };
  }

  const accumulatedDelta =
    now - state.lastEventAt > cooldownMs ? deltaY : state.accumulatedDelta + deltaY;

  if (Math.abs(accumulatedDelta) < threshold) {
    return {
      direction: 0,
      state: {
        accumulatedDelta,
        lastEventAt: now,
        lockedUntil: state.lockedUntil,
      },
    };
  }

  return {
    direction: accumulatedDelta > 0 ? 1 : -1,
    state: {
      accumulatedDelta: 0,
      lastEventAt: now,
      lockedUntil: now + cooldownMs,
    },
  };
}

export function clampSceneIndex(index: number, count: number): number {
  if (count <= 0) return 0;
  return Math.min(Math.max(index, 0), count - 1);
}

export function adjacentSceneIndex(active: number, deltaY: number, count: number): number {
  if (deltaY === 0) return clampSceneIndex(active, count);
  return clampSceneIndex(active + (deltaY > 0 ? 1 : -1), count);
}

export function sceneState(index: number, active: number): SceneState {
  if (index === active) return "active";
  return index < active ? "before" : "after";
}
