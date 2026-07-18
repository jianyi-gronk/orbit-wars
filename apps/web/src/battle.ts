export type PlanetView = {
  id: number;
  owner: -1 | 0 | 1;
  x: number;
  y: number;
  radius: number;
  ships: number;
  production: number;
};

export type PendingLaunch = {
  fromPlanetId: number;
  angle: number;
  ships: number;
};

export type CommandDraft = {
  selectedPlanetId: number | null;
  angle: number;
  ships: number;
  pending: PendingLaunch[];
  error: string | null;
};

export const initialDraft: CommandDraft = {
  selectedPlanetId: null,
  angle: 0,
  ships: 1,
  pending: [],
  error: null,
};

export function selectPlanet(
  draft: CommandDraft,
  planets: PlanetView[],
  player: 0 | 1,
  planetId: number,
): CommandDraft {
  const planet = planets.find((candidate) => candidate.id === planetId);
  if (!planet || planet.owner !== player) {
    return { ...draft, error: "只能从己方星球发出指令。" };
  }
  return {
    ...draft,
    selectedPlanetId: planet.id,
    ships: Math.max(1, Math.min(Math.floor(planet.ships), draft.ships)),
    error: null,
  };
}

export function setAngle(draft: CommandDraft, angle: number): CommandDraft {
  const normalized = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return { ...draft, angle: normalized, error: null };
}

export function setShips(
  draft: CommandDraft,
  planets: PlanetView[],
  requested: number,
): CommandDraft {
  const planet = planets.find((candidate) => candidate.id === draft.selectedPlanetId);
  const available = planet ? Math.floor(planet.ships) : 1;
  return { ...draft, ships: Math.max(1, Math.min(available, Math.floor(requested))) };
}

export function queueLaunch(draft: CommandDraft, planets: PlanetView[]): CommandDraft {
  if (draft.selectedPlanetId === null) {
    return { ...draft, error: "先选择一颗己方星球。" };
  }
  if (draft.pending.length >= 6) {
    return { ...draft, error: "每回合最多六条发射指令。" };
  }
  const planet = planets.find((candidate) => candidate.id === draft.selectedPlanetId);
  const alreadyQueued = draft.pending
    .filter((command) => command.fromPlanetId === draft.selectedPlanetId)
    .reduce((total, command) => total + command.ships, 0);
  if (!planet || alreadyQueued + draft.ships > planet.ships) {
    return { ...draft, error: "待提交兵力超过当前库存。" };
  }
  return {
    ...draft,
    pending: [
      ...draft.pending,
      { fromPlanetId: draft.selectedPlanetId, angle: draft.angle, ships: draft.ships },
    ],
    error: null,
  };
}

export function serverRejected(draft: CommandDraft, code: string): CommandDraft {
  return { ...draft, error: `服务器拒绝：${code}` };
}
