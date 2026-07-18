export type SceneState = "before" | "active" | "after";

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
