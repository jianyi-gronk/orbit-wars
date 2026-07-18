import { apiUrl } from "./api";
import type { Locale } from "./i18n";

export type PublicReplayEvent = {
  step: number;
  type: string;
  slot?: number | null;
  [key: string]: unknown;
};

export type CompactReplay = {
  publicId: string;
  matchPublicId: string | null;
  mapId: string | null;
  mode: string | null;
  frameCount: number;
  result: { winnerSlot?: number | null; reason?: string; finalStep?: number } | null;
  participants: Array<{
    slot: number;
    fleetName?: string;
    fleetPublicId?: string;
    controllerType?: string;
    strategyVersionId?: string | null;
    submittedBy?: string | null;
  }>;
  ratingChanges: Array<{ fleetPublicId?: string; delta?: number }>;
  events: PublicReplayEvent[];
  facts: string[] | string;
  deepLinks: { artifact: string; segmentTemplate: string };
};

export type PublicMatchSummary = {
  publicId: string;
  mode: string;
  mapId: string;
  result: { winnerSlot?: number | null; reason?: string } | null;
  replayPublicId: string;
  replayArtifact: {
    schemaVersion: number;
    frameCount: number;
    sizeBytes: number;
    savedAt: string;
  };
  createdAt: string;
  featured: boolean;
  intensity: {
    score: number;
    band: "routine" | "contested" | "volatile";
    signals: string[];
    featured: boolean;
  };
  highlights: PublicReplayEvent[];
  participants: Array<{
    slot: number;
    fleetPublicId: string;
    fleetName: string;
    controllerType: "human" | "agent";
    strategyVersionId: string | null;
    submittedBy: string | null;
    ratingChange: { delta?: number } | null;
  }>;
};

export function replayEventName(locale: Locale, type: string): string {
  const labels: Record<string, [string, string]> = {
    home_planet_lost: ["母星失守", "Home planet lost"],
    largest_launch: ["最大出击", "Largest launch"],
    match_finished: ["比赛结束", "Match finished"],
    planet_captured: ["星球易手", "Planet captured"],
    player_eliminated: ["舰队淘汰", "Fleet eliminated"],
    production_lead_changed: ["产能领先变化", "Production lead changed"],
    ship_lead_changed: ["兵力领先变化", "Ship lead changed"],
  };
  return labels[type]?.[locale === "zh" ? 0 : 1] ?? type.replaceAll("_", " ");
}

export function replayReasonName(locale: Locale, reason?: string): string {
  const labels: Record<string, [string, string]> = {
    elimination: ["歼灭对手", "Elimination"],
    timeout: ["时间结束", "Time limit"],
    forfeit: ["对手弃权", "Forfeit"],
    draw: ["平局", "Draw"],
  };
  if (!reason) return locale === "zh" ? "结果已确认" : "Result verified";
  return labels[reason]?.[locale === "zh" ? 0 : 1] ?? reason.replaceAll("_", " ");
}

export function publicReplayDataUrl(publicId: string, origin: string): string {
  return apiUrl(`/api/public/v1/replays/${publicId}/compact`, origin);
}

type AnalysisBriefInput = {
  locale: Locale;
  compact: CompactReplay;
  replayUrl: string;
  dataUrl: string;
};

export function buildAgentAnalysisBrief({
  locale,
  compact,
  replayUrl,
  dataUrl,
}: AnalysisBriefInput): string {
  const zh = locale === "zh";
  const facts = Array.isArray(compact.facts) ? compact.facts : compact.facts ? [compact.facts] : [];
  const payload = {
    replay: replayUrl,
    compactData: dataUrl,
    matchId: compact.matchPublicId,
    map: compact.mapId,
    mode: compact.mode,
    frameCount: compact.frameCount,
    participants: compact.participants.map((participant) => ({
      slot: participant.slot,
      fleet: participant.fleetName,
      controller: participant.controllerType,
      strategyVersion: participant.strategyVersionId,
    })),
    result: compact.result,
    ratingChanges: compact.ratingChanges,
    facts,
    keyEvents: compact.events.slice(0, 20),
  };
  const instruction = zh
    ? "请读取以下公开 compact replay，分析双方关键决策、胜负转折和当前策略的具体缺陷；提出 3 个可验证的下一版本改动，并为每项给出模拟指标。不要猜测未出现在权威数据中的行为。"
    : "Read this public compact replay. Analyze both sides' key decisions, turning points, and concrete strategy defects. Propose three testable changes for the next version with simulation metrics. Do not infer behavior absent from authoritative data.";
  return `${instruction}\n\n${JSON.stringify(payload, null, 2)}`;
}
