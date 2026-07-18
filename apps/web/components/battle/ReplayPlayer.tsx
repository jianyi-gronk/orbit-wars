"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError, apiFetchWithRetry } from "../../src/api";
import {
  checkpointForStep,
  formatRatingDelta,
  reconstructSegment,
  type ReplayFrame,
  type ReplayRecord,
} from "../../src/replay";
import { errorMessage, localPath, messages, type Locale } from "../../src/i18n";
import { BattleStage } from "./BattleStage";

type ReplayEvent = { step: number; type: string; slot?: number | null; [key: string]: unknown };
type CompactReplay = {
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
  events: ReplayEvent[];
  facts: string[] | string;
  deepLinks: { artifact: string; segmentTemplate: string };
};

function eventName(locale: Locale, type: string): string {
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

function eventPosition(step: number, frameCount: number | undefined): number {
  return Math.max(0, Math.min(100, frameCount ? (step / Math.max(1, frameCount - 1)) * 100 : 0));
}

function eventEdge(position: number): "start" | "middle" | "end" {
  if (position < 8) return "start";
  if (position > 92) return "end";
  return "middle";
}

export function ReplayPlayer({ publicId, locale = "zh" }: { publicId: string; locale?: Locale }) {
  const zh = locale === "zh";
  const [frames, setFrames] = useState<ReplayFrame[]>([]);
  const [compact, setCompact] = useState<CompactReplay | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loadingSegments, setLoadingSegments] = useState(0);
  const [error, setError] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      let stage = "COMPACT";
      try {
        const summary = await apiFetchWithRetry<CompactReplay>(
          `/api/public/v1/replays/${publicId}/compact`,
          { signal: controller.signal },
        );
        setCompact(summary);
        const checkpoints = Array.from(
          { length: Math.max(1, Math.ceil(summary.frameCount / 20)) },
          (_, index) => index * 20,
        );
        setLoadingSegments(checkpoints.length);
        const loaded: ReplayFrame[] = [];
        for (const checkpoint of checkpoints) {
          stage = `SEGMENT ${checkpoint}`;
          const records = await apiFetchWithRetry<ReplayRecord[]>(
            `/api/public/v1/replays/${publicId}/segments/${checkpoint}`,
            { signal: controller.signal },
          );
          loaded.push(...reconstructSegment(records));
          loaded.sort((a, b) => a.step - b.step);
          setFrames([...loaded]);
          setLoadingSegments((value) => Math.max(0, value - 1));
        }
      } catch (reason) {
        if (reason instanceof Error && reason.name === "AbortError") return;
        const code =
          reason instanceof ApiError
            ? reason.code
            : reason instanceof Error
              ? reason.name
              : "unknown";
        const description = reason instanceof Error ? reason.message : String(reason);
        setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
        setErrorDetail(
          process.env.NODE_ENV === "production"
            ? `${stage} / ${code}`
            : `${stage} / ${code} / ${description}`,
        );
        if (process.env.NODE_ENV !== "production") {
          console.warn("Replay load failed", { publicId, stage, reason });
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [loadAttempt, locale, publicId]);

  useEffect(() => {
    if (!playing || frames.length < 2) return;
    const timer = window.setInterval(
      () => setStepIndex((value) => (value >= frames.length - 1 ? 0 : value + 1)),
      500 / speed,
    );
    return () => window.clearInterval(timer);
  }, [frames.length, playing, speed]);

  const frame = frames[Math.min(stepIndex, Math.max(0, frames.length - 1))];
  const events = useMemo(() => compact?.events ?? [], [compact?.events]);
  const currentEvent = useMemo(
    () => [...events].reverse().find((event) => event.step <= (frame?.step ?? 0)),
    [events, frame?.step],
  );
  const sides = compact?.participants ?? [];
  const facts = compact?.facts
    ? Array.isArray(compact.facts)
      ? compact.facts
      : [compact.facts]
    : [];
  const currentStep = frame?.step ?? 0;
  const frameStatus = compact
    ? zh
      ? `${frames.length}/${compact.frameCount} 帧权威数据${loadingSegments ? ` · 正在载入 ${loadingSegments} 个分段` : " · 已完整载入"}`
      : `${frames.length}/${compact.frameCount} authoritative frames${loadingSegments ? ` · loading ${loadingSegments} segments` : " · fully loaded"}`
    : messages[locale].common.loading;
  const resultSummary =
    compact?.result?.winnerSlot == null
      ? zh
        ? "无唯一胜方"
        : "No sole winner"
      : `${zh ? "胜方槽位" : "Winner slot"} ${compact.result.winnerSlot}`;

  function retryLoad() {
    setError("");
    setErrorDetail("");
    setCompact(null);
    setFrames([]);
    setStepIndex(0);
    setPlaying(false);
    setLoadingSegments(0);
    setLoadAttempt((value) => value + 1);
  }

  if (error)
    return (
      <main className="replay-shell">
        <section className="replay-error-panel">
          <span>REPLAY LINK / OFFLINE</span>
          <h1>{zh ? "无法加载该对局" : "Replay unavailable"}</h1>
          <p role="alert">{error}</p>
          <small>{errorDetail}</small>
          <div className="replay-error-actions">
            <button className="replay-back-button" onClick={retryLoad}>
              ↻ {zh ? "重新读取回放" : "Retry replay"}
            </button>
            <Link className="replay-back-button" href={localPath(locale, "/history")}>
              ← {zh ? "返回对局记录" : "Back to encounters"}
            </Link>
          </div>
        </section>
      </main>
    );
  return (
    <main className="replay-shell">
      <header className="replay-header">
        <div className="replay-identity">
          <Link href={localPath(locale, "/history")}>← {zh ? "对局记录" : "ENCOUNTERS"}</Link>
          <span>PUBLIC REPLAY / IMMUTABLE</span>
          <strong title={publicId}>{publicId}</strong>
        </div>
        <div className="replay-sides">
          <div className="replay-side replay-side--blue">
            <span>01 / {zh ? "蓝方" : "BLUE"}</span>
            <b title={sides[0]?.fleetName}>{sides[0]?.fleetName ?? "—"}</b>
            <small>{sides[0]?.controllerType?.toUpperCase() ?? "AGENT"}</small>
          </div>
          <em>VS</em>
          <div className="replay-side replay-side--red">
            <span>02 / {zh ? "红方" : "RED"}</span>
            <b title={sides[1]?.fleetName}>{sides[1]?.fleetName ?? "—"}</b>
            <small>{sides[1]?.controllerType?.toUpperCase() ?? "AGENT"}</small>
          </div>
        </div>
        <div className="replay-rating">
          <span>RATING Δ</span>
          <strong>
            {compact?.ratingChanges.map((item) => formatRatingDelta(item.delta)).join(" / ") || "—"}
          </strong>
          <small>{compact?.mode?.toUpperCase() ?? "PUBLIC MATCH"}</small>
        </div>
      </header>
      <section className="replay-stage-wrap">
        {frame ? (
          <BattleStage
            planets={frame.planets}
            player={0}
            selectedPlanetId={null}
            angle={0}
            lowPerformance={false}
            showPlanetIds={false}
            onSelect={() => undefined}
            onAim={() => undefined}
          />
        ) : (
          <div className="battle-stage" role="status">
            <span className="replay-stage-loading">{messages[locale].common.loading}</span>
          </div>
        )}
        <div className="replay-grid-overlay" aria-hidden="true" />
        <div className="replay-corner replay-corner--tl" aria-hidden="true" />
        <div className="replay-corner replay-corner--br" aria-hidden="true" />
        <div className="replay-step">
          <span>AUTHORITATIVE FRAME</span>
          STEP {String(currentStep).padStart(3, "0")}
        </div>
        <div className="replay-map-label">
          {compact?.mapId ?? "ORBITAL GRID"} / {compact?.frameCount ?? "—"} STEPS
        </div>
        {currentEvent && (
          <div className="replay-callout">
            <span>{zh ? "最近战场事件" : "LATEST FIELD EVENT"}</span>
            <strong>{eventName(locale, currentEvent.type)}</strong>
            <small>
              STEP {currentEvent.step} · SLOT {currentEvent.slot ?? "—"}
            </small>
          </div>
        )}
      </section>
      <section className="replay-console">
        <div className="replay-controls-row">
          <div className="replay-controls">
            <button
              className="replay-play-button"
              disabled={!frames.length}
              onClick={() => setPlaying((value) => !value)}
            >
              <i aria-hidden="true">{playing ? "Ⅱ" : "▶"}</i>
              {playing ? (zh ? "暂停" : "PAUSE") : zh ? "播放" : "PLAY"}
            </button>
            <button
              aria-label={zh ? "上一帧" : "Previous frame"}
              disabled={!frames.length}
              onClick={() => setStepIndex((value) => Math.max(0, value - 1))}
            >
              − 1
            </button>
            <button
              aria-label={zh ? "下一帧" : "Next frame"}
              disabled={!frames.length}
              onClick={() =>
                setStepIndex((value) => Math.min(Math.max(0, frames.length - 1), value + 1))
              }
            >
              + 1
            </button>
            <label className="replay-speed">
              <span>{zh ? "倍速" : "SPEED"}</span>
              <select
                aria-label={zh ? "回放速度" : "Replay speed"}
                value={speed}
                onChange={(event) => setSpeed(Number(event.target.value))}
              >
                {[0.5, 1, 2, 4].map((value) => (
                  <option key={value} value={value}>
                    {value}×
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="replay-load-state" aria-live="polite">
            <i className={loadingSegments ? "is-loading" : ""} aria-hidden="true" />
            {frameStatus}
          </p>
        </div>
        <div className="replay-timeline-wrap">
          <div className="replay-timeline-meta">
            <span>000</span>
            <strong>
              {zh ? "战场时间轴" : "BATTLE TIMELINE"} / {events.length} {zh ? "个事件" : "EVENTS"}
            </strong>
            <span>{String(compact?.frameCount ?? 0).padStart(3, "0")}</span>
          </div>
          <input
            className="replay-timeline"
            type="range"
            min="0"
            max={Math.max(0, frames.length - 1)}
            value={stepIndex}
            aria-label={zh ? "回放时间线" : "Replay timeline"}
            onChange={(event) => setStepIndex(Number(event.target.value))}
          />
          <div className="replay-event-track" aria-label={zh ? "关键事件" : "Key events"}>
            {events.map((event, index) => {
              const position = eventPosition(event.step, compact?.frameCount);
              const label = `${event.step} / ${eventName(locale, event.type)}`;
              return (
                <button
                  aria-label={label}
                  data-active={event === currentEvent || undefined}
                  data-edge={eventEdge(position)}
                  key={`${event.step}-${event.type}-${index}`}
                  onClick={() => {
                    const target = checkpointForStep(event.step, 1);
                    const found = frames.findIndex((item) => item.step >= target);
                    if (found >= 0) setStepIndex(found);
                  }}
                  style={{ left: `${position}%` }}
                >
                  <i aria-hidden="true" />
                  <span>{label}</span>
                </button>
              );
            })}
          </div>
        </div>
        <aside className="replay-facts">
          <div className="replay-facts-label">
            <span>RESULT / VERIFIED</span>
            <strong>{zh ? "事实型胜因" : "AUTHORITATIVE RESULT"}</strong>
          </div>
          <div className="replay-facts-result">
            <strong>
              {zh && facts[0] ? facts[0] : `${compact?.result?.reason ?? "—"} · ${resultSummary}`}
            </strong>
            <span>
              {zh
                ? "说明只取自权威帧与命令，不使用生成式推断。"
                : "This display uses authoritative frames and commands only; no generated inference."}
            </span>
          </div>
          {compact?.deepLinks.artifact && (
            <a className="replay-artifact-link" href={compact.deepLinks.artifact}>
              {zh ? "打开原始回放" : "OPEN RAW ARTIFACT"} ↗
            </a>
          )}
        </aside>
      </section>
    </main>
  );
}
