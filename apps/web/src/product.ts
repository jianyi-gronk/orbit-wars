export type MatchMode = "training" | "ranked";
export type ControlFilter = "all" | "human" | "agent";

export function canQueue(mode: MatchMode, confirmed: boolean): boolean {
  return mode === "training" || confirmed;
}

export function filterByControl<T extends { controlTags: string }>(
  entries: T[],
  filter: string,
): T[] {
  if (filter === "all") return entries;
  return entries.filter((entry) => entry.controlTags.toLowerCase().includes(filter));
}

export function canRevealAgentSecret(justIssued: boolean): boolean {
  return justIssued;
}
