export type FrameBudgetReport = {
  targetFps: 30 | 60;
  budgetMs: number;
  p95Ms: number;
  withinBudget: boolean;
};

export function frameBudgetReport(samplesMs: number[], lowPerformance: boolean): FrameBudgetReport {
  const targetFps = lowPerformance ? 30 : 60;
  const budgetMs = 1000 / targetFps;
  const ordered = [...samplesMs].sort((left, right) => left - right);
  const index = Math.max(0, Math.ceil(ordered.length * 0.95) - 1);
  const p95Ms = ordered[index] ?? 0;
  return { targetFps, budgetMs, p95Ms, withinBudget: p95Ms <= budgetMs };
}

export function replaySeekReadBound(targetStep: number, checkpointInterval = 20): number {
  if (targetStep < 0 || checkpointInterval <= 0) throw new Error("invalid seek target");
  return (targetStep % checkpointInterval) + 1;
}
