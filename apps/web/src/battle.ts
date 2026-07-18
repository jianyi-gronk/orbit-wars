export type PlanetView = {
  id: number;
  owner: -1 | 0 | 1;
  x: number;
  y: number;
  radius: number;
  ships: number;
  production: number;
};

export type FleetView = {
  id: number;
  owner: 0 | 1;
  x: number;
  y: number;
  angle: number;
  fromPlanetId: number;
  ships: number;
};

export const BATTLEFIELD_SIZE = 100;
export const SUN_CENTER = BATTLEFIELD_SIZE / 2;
export const SUN_RADIUS = 10;

export type BattlefieldViewport = {
  size: number;
  scale: number;
  offsetX: number;
  offsetY: number;
};

export function battlefieldViewport(width: number, height: number): BattlefieldViewport {
  const size = Math.max(0, Math.min(width, height));
  return {
    size,
    scale: size / BATTLEFIELD_SIZE,
    offsetX: (width - size) / 2,
    offsetY: (height - size) / 2,
  };
}

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

export function formatPlanetLabel(id: number, ships: number, showId = true): string {
  const currentShips = Math.floor(ships);
  return showId ? `${id} · ${currentShips}` : String(currentShips);
}

export function fleetDirection(angle: number): { x: number; y: number } {
  return { x: Math.cos(angle), y: Math.sin(angle) };
}

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
  const available = planet ? availableShips(draft, planets, planet.id) : 1;
  return { ...draft, ships: Math.max(1, Math.min(available, Math.floor(requested))) };
}

export function queuedShipsForPlanet(
  draft: CommandDraft,
  planetId: number,
  excludeIndex: number | null = null,
): number {
  return draft.pending.reduce(
    (total, command, index) =>
      index !== excludeIndex && command.fromPlanetId === planetId ? total + command.ships : total,
    0,
  );
}

export function availableShips(
  draft: CommandDraft,
  planets: PlanetView[],
  planetId: number,
): number {
  const planet = planets.find((candidate) => candidate.id === planetId);
  return Math.max(0, Math.floor(planet?.ships ?? 0) - queuedShipsForPlanet(draft, planetId));
}

export function aimAtPoint(
  draft: CommandDraft,
  planets: PlanetView[],
  targetX: number,
  targetY: number,
): CommandDraft {
  const source = planets.find((candidate) => candidate.id === draft.selectedPlanetId);
  if (!source) return { ...draft, error: "先选择一颗己方星球。" };
  return setAngle(draft, Math.atan2(targetY - source.y, targetX - source.x));
}

export function setShipRatio(
  draft: CommandDraft,
  planets: PlanetView[],
  ratio: number,
): CommandDraft {
  if (draft.selectedPlanetId === null) return { ...draft, error: "先选择一颗己方星球。" };
  const available = availableShips(draft, planets, draft.selectedPlanetId);
  return {
    ...draft,
    ships: Math.max(1, Math.floor(available * Math.max(0, Math.min(1, ratio)))),
    error: null,
  };
}

export function removeQueuedLaunch(draft: CommandDraft, index: number): CommandDraft {
  return {
    ...draft,
    pending: draft.pending.filter((_command, commandIndex) => commandIndex !== index),
    error: null,
  };
}

export function updateQueuedLaunch(
  draft: CommandDraft,
  planets: PlanetView[],
  index: number,
  requestedShips: number,
): CommandDraft {
  const command = draft.pending[index];
  if (!command) return draft;
  const planet = planets.find((candidate) => candidate.id === command.fromPlanetId);
  const remaining = Math.max(
    1,
    Math.floor(planet?.ships ?? 1) - queuedShipsForPlanet(draft, command.fromPlanetId, index),
  );
  return {
    ...draft,
    pending: draft.pending.map((candidate, commandIndex) =>
      commandIndex === index
        ? { ...candidate, ships: Math.max(1, Math.min(remaining, Math.floor(requestedShips))) }
        : candidate,
    ),
    error: null,
  };
}

export function queueLaunch(draft: CommandDraft, planets: PlanetView[]): CommandDraft {
  if (draft.selectedPlanetId === null) {
    return { ...draft, error: "先选择一颗己方星球。" };
  }
  if (draft.pending.length >= 6) {
    return { ...draft, error: "每回合最多六条发射指令。" };
  }
  const planet = planets.find((candidate) => candidate.id === draft.selectedPlanetId);
  const alreadyQueued = queuedShipsForPlanet(draft, draft.selectedPlanetId);
  if (!planet || alreadyQueued + draft.ships > planet.ships) {
    return { ...draft, error: "待提交兵力超过当前库存。" };
  }
  return {
    ...draft,
    ships: Math.max(
      1,
      Math.min(draft.ships, Math.floor(planet.ships) - alreadyQueued - draft.ships),
    ),
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
