import type { FleetView, PlanetView } from "./battle";

export type ReplayFrame = {
  step: number;
  planets: PlanetView[];
  fleets: FleetView[];
  stateHash: string;
};
export type ReplayRecord =
  | {
      type: "checkpoint" | "delta";
      frame: { step: number; stateHash?: string; planets?: number[][]; fleets?: number[][] };
    }
  | { type: "result"; result?: Record<string, unknown> };

function planets(rows: number[][]): PlanetView[] {
  return rows.map((row) => ({
    id: row[0],
    owner: row[1] as -1 | 0 | 1,
    x: row[2],
    y: row[3],
    radius: row[4],
    ships: row[5],
    production: row[6],
  }));
}

function fleets(rows: number[][]): FleetView[] {
  return rows.map((row) => ({
    id: row[0],
    owner: row[1] as 0 | 1,
    x: row[2],
    y: row[3],
    angle: row[4],
    fromPlanetId: row[5],
    ships: row[6],
  }));
}

export function reconstructSegment(records: ReplayRecord[]): ReplayFrame[] {
  const frames: ReplayFrame[] = [];
  let current: ReplayFrame | null = null;
  for (const record of records) {
    if (record.type === "checkpoint") {
      if (!record.frame.planets) throw new Error("checkpoint has no planets");
      current = {
        step: record.frame.step,
        stateHash: record.frame.stateHash ?? "",
        planets: planets(record.frame.planets),
        fleets: fleets(record.frame.fleets ?? []),
      };
    } else if (record.type === "delta" && current) {
      current = {
        step: record.frame.step,
        stateHash: record.frame.stateHash ?? current.stateHash,
        planets: record.frame.planets ? planets(record.frame.planets) : current.planets,
        fleets: record.frame.fleets ? fleets(record.frame.fleets) : current.fleets,
      };
    } else continue;
    if (current) frames.push(current);
  }
  return frames;
}

export function checkpointForStep(step: number, interval = 20) {
  return Math.max(0, Math.floor(step / interval) * interval);
}

export function formatRatingDelta(value?: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const rounded = Math.abs(value) < 0.05 ? 0 : Math.round(value * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)}`;
}
