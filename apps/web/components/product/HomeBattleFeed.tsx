"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiFetchWithRetry } from "../../src/api";
import { formatDate, localPath, type Locale } from "../../src/i18n";
import type { CompactReplay, PublicMatchSummary } from "../../src/public-replay";
import { reconstructSegment, type ReplayFrame, type ReplayRecord } from "../../src/replay";
import { BattleStage } from "../battle/BattleStage";

type HomeBattleData = {
  matches: PublicMatchSummary[];
  compact: CompactReplay | null;
  frames: ReplayFrame[];
};

let homeBattleDataPromise: Promise<HomeBattleData> | null = null;

function loadHomeBattleData(): Promise<HomeBattleData> {
  if (homeBattleDataPromise) return homeBattleDataPromise;
  homeBattleDataPromise = apiFetchWithRetry<{ matches: PublicMatchSummary[] }>(
    "/api/public/v1/matches?period=all&limit=3",
    {},
    { attempts: 3 },
  )
    .then(async ({ matches }) => {
      const match = matches.find((item) => item.replayPublicId);
      if (!match) return { matches, compact: null, frames: [] };
      try {
        const [compact, records] = await Promise.all([
          apiFetchWithRetry<CompactReplay>(
            `/api/public/v1/replays/${match.replayPublicId}/compact`,
          ),
          apiFetchWithRetry<ReplayRecord[]>(
            `/api/public/v1/replays/${match.replayPublicId}/segments/0`,
          ),
        ]);
        return { matches, compact, frames: reconstructSegment(records).slice(0, 20) };
      } catch {
        return { matches, compact: null, frames: [] };
      }
    })
    .catch((reason) => {
      homeBattleDataPromise = null;
      throw reason;
    });
  return homeBattleDataPromise;
}

function winnerName(match: PublicMatchSummary | undefined, locale: Locale): string {
  if (!match) return "—";
  const winner = match.participants.find((item) => item.slot === match.result?.winnerSlot);
  return winner?.fleetName ?? (locale === "zh" ? "平局" : "Draw");
}

function versus(match: PublicMatchSummary): string {
  return match.participants.map((item) => item.fleetName).join(" / ");
}

export function HomeBattleFeed({
  active,
  locale,
  reducedMotion,
  variant,
}: {
  active: boolean;
  locale: Locale;
  reducedMotion: boolean;
  variant: "preview" | "latest";
}) {
  const zh = locale === "zh";
  const [data, setData] = useState<HomeBattleData | null>(null);
  const [failed, setFailed] = useState(false);
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    let disposed = false;
    void loadHomeBattleData()
      .then((value) => {
        if (!disposed) setData(value);
      })
      .catch(() => {
        if (!disposed) setFailed(true);
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (variant !== "preview" || !active || reducedMotion || !data || data.frames.length < 2)
      return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setFrameIndex((value) => (value + 1) % data.frames.length);
    }, 620);
    return () => window.clearInterval(timer);
  }, [active, data, reducedMotion, variant]);

  const match = data?.matches[0];
  const frame = data?.frames[Math.min(frameIndex, Math.max(0, data.frames.length - 1))];
  const emptyCopy = failed
    ? zh
      ? "公开战场暂时离线"
      : "Public battlefield temporarily offline"
    : zh
      ? "正在接入公开战场…"
      : "Connecting to the public battlefield…";
  const result = useMemo(
    () => (match ? `${zh ? "胜方" : "WINNER"} / ${winnerName(match, locale)}` : emptyCopy),
    [emptyCopy, locale, match, zh],
  );

  if (variant === "latest") {
    return (
      <div className="home-latest-matches" aria-label={zh ? "最近公开对局" : "Latest public matches"}>
        <header>
          <span>LIVE ARCHIVE</span>
          <strong>{zh ? "最近公开对局" : "LATEST ENCOUNTERS"}</strong>
        </header>
        {!data?.matches.length ? (
          <div className="home-match-empty" role="status">
            {emptyCopy}
          </div>
        ) : (
          data.matches.map((item, index) => (
            <Link
              className="home-match-card"
              href={localPath(locale, `/replay/${item.replayPublicId}`)}
              key={item.publicId}
            >
              <span>0{index + 1}</span>
              <div>
                <strong>{versus(item)}</strong>
                <small>
                  {item.mode.toUpperCase()} · {item.mapId} · {formatDate(locale, item.createdAt)}
                </small>
              </div>
              <b>{winnerName(item, locale)} ↗</b>
            </Link>
          ))
        )}
      </div>
    );
  }

  return (
    <div className="home-battle-preview" data-ready={Boolean(frame)}>
      <div className="home-battle-preview__stage">
        {frame ? (
          <BattleStage
            angle={0}
            fleets={frame.fleets}
            lowPerformance
            onAim={() => undefined}
            onSelect={() => undefined}
            planets={frame.planets}
            player={0}
            selectedPlanetId={null}
            showPlanetIds={false}
          />
        ) : (
          <div className="home-battle-preview__fallback" role="status">
            <i aria-hidden="true" />
            <span>{emptyCopy}</span>
          </div>
        )}
      </div>
      <div className="home-battle-preview__scan" aria-hidden="true" />
      <header>
        <span>PUBLIC RELAY / {match?.mode?.toUpperCase() ?? "STANDBY"}</span>
        <strong>{match ? versus(match) : "ORBIT/WARS"}</strong>
      </header>
      <footer>
        <span>STEP {String(frame?.step ?? 0).padStart(3, "0")}</span>
        <strong>{result}</strong>
      </footer>
      {match?.replayPublicId && (
        <Link
          aria-label={zh ? `观看 ${versus(match)} 的回放` : `Watch ${versus(match)} replay`}
          className="home-battle-preview__link"
          href={localPath(locale, `/replay/${match.replayPublicId}`)}
        >
          {zh ? "进入回放" : "OPEN REPLAY"} ↗
        </Link>
      )}
    </div>
  );
}
