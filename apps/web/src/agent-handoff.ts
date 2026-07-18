import type { Locale } from "./i18n";

export type CommandMission =
  "copy-handoff" | "needs-agent-key" | "needs-ready-strategy" | "battle-ready";

export function resolveCommandMission({
  secret,
  hasActiveKey,
  currentStrategyStatus,
}: {
  secret: string | null;
  hasActiveKey: boolean;
  currentStrategyStatus: string | null;
}): CommandMission {
  if (secret) return "copy-handoff";
  if (!hasActiveKey) return "needs-agent-key";
  if (currentStrategyStatus !== "ready") return "needs-ready-strategy";
  return "battle-ready";
}

export function buildAgentHandoffBundle({
  locale,
  key,
  fleetId,
  apiBaseUrl,
  guideUrl,
}: {
  locale: Locale;
  key: string;
  fleetId: string;
  apiBaseUrl: string;
  guideUrl: string;
}): string {
  const instruction =
    locale === "zh"
      ? "先读取舰队、版本、推荐对手和近期比赛；确认当前 ready 策略后，发起一场训练挑战。除非我明确要求，不要参加排位，也不要在日志、聊天或仓库中保存密钥。"
      : "First read the fleet, versions, recommended opponents, and recent matches. Confirm the current ready strategy, then start one training challenge. Do not enter ranked play unless I explicitly ask, and never save the key in logs, chat, or the repository.";
  return [
    "ORBIT/WARS — AGENT HANDOFF",
    `API Base: ${apiBaseUrl}`,
    `Guide: ${guideUrl}`,
    `Fleet ID: ${fleetId}`,
    `Authorization: Bearer ${key}`,
    "",
    instruction,
  ].join("\n");
}
