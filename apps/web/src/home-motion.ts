export type SceneState = "before" | "active" | "after";

export type WheelGestureState = {
  accumulatedDelta: number;
  lastEventAt: number;
  lastDelta: number;
  lockedAt: number;
  lockedDirection: -1 | 0 | 1;
  lockedUntil: number;
};

export type WheelGestureResult = {
  direction: -1 | 0 | 1;
  state: WheelGestureState;
};

export const HOME_WHEEL_INTENT_THRESHOLD = 100;
export const HOME_WHEEL_INTENT_WINDOW_MS = 420;
export const HOME_WHEEL_GESTURE_RELEASE_MS = 180;
export const HOME_WHEEL_REENTRY_GUARD_MS = 120;
export const HOME_WHEEL_REENTRY_ACCELERATION_RATIO = 1.5;
export const HOME_WHEEL_REENTRY_MIN_DELTA = 12;
export const HOME_WHEEL_MOMENTUM_TAIL_MAX_DELTA = 40;

export function createWheelGestureState(): WheelGestureState {
  return {
    accumulatedDelta: 0,
    lastEventAt: Number.NEGATIVE_INFINITY,
    lastDelta: 0,
    lockedAt: Number.NEGATIVE_INFINITY,
    lockedDirection: 0,
    lockedUntil: 0,
  };
}

export function reduceWheelGesture(
  state: WheelGestureState,
  deltaY: number,
  now: number,
  threshold = HOME_WHEEL_INTENT_THRESHOLD,
  intentWindowMs = HOME_WHEEL_INTENT_WINDOW_MS,
  gestureReleaseMs = HOME_WHEEL_GESTURE_RELEASE_MS,
  reentryGuardMs = HOME_WHEEL_REENTRY_GUARD_MS,
  reentryAccelerationRatio = HOME_WHEEL_REENTRY_ACCELERATION_RATIO,
  reentryMinDelta = HOME_WHEEL_REENTRY_MIN_DELTA,
  momentumTailMaxDelta = HOME_WHEEL_MOMENTUM_TAIL_MAX_DELTA,
): WheelGestureResult {
  if (!Number.isFinite(deltaY) || deltaY === 0 || !Number.isFinite(now)) {
    return { direction: 0, state };
  }

  if (now < state.lockedUntil) {
    const eventDirection = deltaY > 0 ? 1 : -1;
    const reversesLockedDirection = eventDirection !== state.lockedDirection;
    const restartsAfterMomentum =
      now - state.lockedAt >= reentryGuardMs &&
      Math.abs(state.lastDelta) <= momentumTailMaxDelta &&
      Math.abs(deltaY) >= reentryMinDelta &&
      Math.abs(deltaY) >= Math.abs(state.lastDelta) * reentryAccelerationRatio;

    if (!reversesLockedDirection && !restartsAfterMomentum) {
      return {
        direction: 0,
        state: {
          ...state,
          accumulatedDelta: 0,
          lastEventAt: now,
          lastDelta: deltaY,
          lockedUntil: now + gestureReleaseMs,
        },
      };
    }

    state = createWheelGestureState();
  }

  const directionChanged =
    state.accumulatedDelta !== 0 && Math.sign(state.accumulatedDelta) !== Math.sign(deltaY);
  const accumulatedDelta =
    now - state.lastEventAt > intentWindowMs || directionChanged
      ? deltaY
      : state.accumulatedDelta + deltaY;

  if (Math.abs(accumulatedDelta) < threshold) {
    return {
      direction: 0,
      state: {
        accumulatedDelta,
        lastEventAt: now,
        lastDelta: deltaY,
        lockedAt: Number.NEGATIVE_INFINITY,
        lockedDirection: 0,
        lockedUntil: state.lockedUntil,
      },
    };
  }

  return {
    direction: accumulatedDelta > 0 ? 1 : -1,
    state: {
      accumulatedDelta: 0,
      lastEventAt: now,
      lastDelta: deltaY,
      lockedAt: now,
      lockedDirection: accumulatedDelta > 0 ? 1 : -1,
      lockedUntil: now + gestureReleaseMs,
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
