import { localPath, type Locale } from "./i18n";
import { withLoginPrompt } from "./login-modal";

export type MissionState =
  "signed-out" | "needs-fleet" | "needs-strategy" | "battle-ready" | "continue";

export type MissionSnapshot = {
  authenticated: boolean;
  hasFleet?: boolean;
  currentStrategyStatus?: string | null;
  incomplete?: boolean;
};

export type MissionAction = {
  state: MissionState;
  href: string;
  label: string;
};

export function resolveMissionState(snapshot: MissionSnapshot): MissionState {
  if (!snapshot.authenticated) return "signed-out";
  if (snapshot.incomplete) return "continue";
  if (!snapshot.hasFleet) return "needs-fleet";
  if (snapshot.currentStrategyStatus !== "ready") return "needs-strategy";
  return "battle-ready";
}

export function resolveMissionAction(locale: Locale, snapshot: MissionSnapshot): MissionAction {
  const state = resolveMissionState(snapshot);
  const zh = locale === "zh";
  const definitions: Record<MissionState, { path: string; labels: [string, string] }> = {
    "signed-out": { path: "/start", labels: ["开始游戏", "Start playing"] },
    "needs-fleet": { path: "/start", labels: ["创建舰队", "Create fleet"] },
    "needs-strategy": { path: "/strategy-lab", labels: ["优化策略", "Improve strategy"] },
    "battle-ready": { path: "/arena", labels: ["立即开战", "Play now"] },
    continue: { path: "/command", labels: ["继续任务", "Continue mission"] },
  };
  const definition = definitions[state];
  const destination = localPath(locale, definition.path);
  return {
    state,
    href:
      state === "signed-out"
        ? withLoginPrompt(destination, locale)
        : destination,
    label: definition.labels[zh ? 0 : 1],
  };
}
