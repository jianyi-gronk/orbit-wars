export type ApiErrorPayload = { code?: string; message?: string; field?: string };

export type AuthConfig = {
  enabled: boolean;
  passwordEnabled: boolean;
  providers: { github: boolean; google: boolean };
};

export type AuthSession = {
  authenticated: boolean;
  subject?: string;
  displayName?: string | null;
  email?: string | null;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly field?: string,
  ) {
    super(code);
  }
}

const apiBase = process.env.NEXT_PUBLIC_ORBIT_API_BASE ?? "/orbit-api";
const devSubject = process.env.NEXT_PUBLIC_ORBIT_DEV_SUBJECT;

export function apiUrl(path: string, origin?: string): string {
  const value = `${apiBase.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  if (/^https?:\/\//.test(value) || !origin) return value;
  return new URL(value, origin).toString();
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (devSubject) headers.set("X-Orbit-Dev-Subject", devSubject);
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    let detail: ApiErrorPayload = {};
    try {
      const payload = (await response.json()) as { detail?: ApiErrorPayload | string };
      detail = typeof payload.detail === "object" && payload.detail ? payload.detail : {};
    } catch {
      // A stable status fallback is more useful than hiding a non-JSON upstream failure.
    }
    throw new ApiError(response.status, detail.code ?? `http.${response.status}`, detail.field);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

type ApiRetryOptions = {
  attempts?: number;
  baseDelayMs?: number;
};

function retryable(reason: unknown): boolean {
  if (!(reason instanceof ApiError)) return reason instanceof Error;
  return (
    reason.status === 408 || reason.status === 425 || reason.status === 429 || reason.status >= 500
  );
}

function retryDelay(ms: number, signal: AbortSignal | null | undefined): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Request aborted", "AbortError"));
      return;
    }
    const timer = globalThis.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        globalThis.clearTimeout(timer);
        reject(new DOMException("Request aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export async function apiFetchWithRetry<T>(
  path: string,
  init: RequestInit = {},
  options: ApiRetryOptions = {},
): Promise<T> {
  const attempts = Math.max(1, options.attempts ?? 3);
  const baseDelayMs = Math.max(0, options.baseDelayMs ?? 180);
  let lastReason: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await apiFetch<T>(path, init);
    } catch (reason) {
      lastReason = reason;
      if (
        (reason instanceof Error && reason.name === "AbortError") ||
        !retryable(reason) ||
        attempt === attempts - 1
      ) {
        throw reason;
      }
      await retryDelay(baseDelayMs * 2 ** attempt, init.signal);
    }
  }
  throw lastReason;
}

export function idempotencyKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

export type Fleet = {
  publicId: string;
  name: string;
  commanderCode: string;
  declaration: string;
  strategyTendency: string;
  styleDescription: string;
  currentStrategyVersionId?: string | null;
  currentStrategyStatus?: string | null;
  createdAt: string;
};

export type CompetitiveRank = {
  tier: "bronze" | "silver" | "gold" | "platinum" | "diamond" | "master";
  division: "III" | "II" | "I" | null;
  points: number;
};

export type FleetProfile = Fleet & {
  rating: {
    rank: number | null;
    tier: string;
    competitiveRank: CompetitiveRank;
    displayScore: number;
    mu: number;
    sigma: number;
  };
  controlTags: Array<"human" | "agent">;
  versions: StrategyVersion[];
  matches: PublicMatch[];
  representativeReplayPublicId: string | null;
};

export type StrategyVersion = {
  publicId: string;
  contentHash?: string;
  status: string;
  notes: string;
  source: string;
  submittedBy?: string;
  createdAt: string;
};

export type AgentKey = {
  publicPrefix: string;
  scopes: string[];
  active: boolean;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
};

export type StrategyDraft = {
  revision: number;
  mode: "guided" | "code";
  sourceCode: string;
  parameters: {
    launchRatio?: number;
    minimumShips?: number;
    targetPreference?: "nearest" | "weakest";
  };
  baseStrategyVersionId: string | null;
  lastValidation: Record<string, unknown> | null;
  validatedContentHash: string | null;
  updatedAt: string;
};

export type StrategyLabWorkspace = {
  fleet: {
    publicId: string;
    name: string;
    currentStrategyVersionId: string | null;
  };
  draft: StrategyDraft;
  versions: Array<StrategyVersion & { validation?: Record<string, unknown> | null }>;
  editableTemplates: Array<{
    id: string;
    name: string;
    editable: boolean;
    source: string;
  }>;
  aiCredits: {
    remaining: number;
    granted: number;
    standardCost: number;
    deepCost: number;
  };
  simulation: LabSimulation | null;
  publishEligibility: {
    eligible: boolean;
    blockingReason: string | null;
  };
};

export type LabSimulation = {
  publicId: string;
  kind: "strategy_simulation";
  visibility: "private";
  status: string;
  result: Record<string, unknown> | null;
  replayPublicId: string | null;
  validationPassed: boolean;
  publishEligible: boolean;
  blockingReason: string | null;
};

export type MatchStatusRecord = {
  publicId: string;
  mode: "training" | "ranked";
  status: string;
  mapId: string;
  matchmakingReason: string | null;
  result: { winnerSlot?: number | null; reason?: string } | null;
  createdAt: string;
  finishedAt: string | null;
  replayPublicId: string | null;
  participants: Array<{
    slot: number;
    fleetPublicId: string;
    fleetName: string;
    controllerType: "human" | "agent";
    strategyVersionId: string | null;
  }>;
};

export type AiAssist = {
  requestId: string;
  summary: string;
  reasoning: string;
  proposedSource: string;
  diff: string;
  tests: string[];
  cost: number;
  remaining: number;
};

export type PublicMatch = {
  publicId: string;
  mode: "training" | "ranked";
  status: string;
  controllerType?: "human" | "agent";
  strategyVersionId?: string | null;
  result?: Record<string, unknown> | null;
  ratingChange?: Record<string, unknown> | null;
  replayPublicId?: string | null;
  createdAt: string;
  participants?: Array<{
    slot: number;
    fleetPublicId: string;
    fleetName: string;
    commanderCode: string;
    controllerType: "human" | "agent";
    strategyVersionId: string | null;
  }>;
};
