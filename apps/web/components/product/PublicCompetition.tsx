"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiFetch,
  apiFetchWithRetry,
  type CompetitiveRank,
  type FleetProfile,
} from "../../src/api";
import { humanPlayEnabled } from "../../src/features";
import {
  errorMessage,
  formatDate,
  formatNumber,
  localPath,
  messages,
  type Locale,
} from "../../src/i18n";
import { competitiveRankLabel, competitiveRankPoints } from "../../src/rating";
import { formatRatingDelta } from "../../src/replay";
import { ModeTag } from "./ModeTag";

type LeaderboardEntry = {
  rank: number;
  fleetPublicId: string;
  name: string;
  commanderCode: string;
  tier: string;
  competitiveRank: CompetitiveRank;
  displayScore: number;
  controlTags: Array<"human" | "agent">;
  record: { matches: number; wins: number; losses: number };
};

export function LeaderboardView({
  locale,
  period,
  control,
}: {
  locale: Locale;
  period: string;
  control: string;
}) {
  const zh = locale === "zh";
  const [entries, setEntries] = useState<LeaderboardEntry[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const controlQuery = control === "all" ? "" : `&controller_type=${control}`;
    void apiFetch<{ entries: LeaderboardEntry[] }>(
      `/api/public/v1/leaderboard?period=${period}${controlQuery}`,
      { signal: controller.signal },
    )
      .then((value) => setEntries(value.entries))
      .catch((reason) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
      });
    return () => controller.abort();
  }, [control, locale, period]);

  function filterLink(nextPeriod: string, nextControl: string) {
    return `${localPath(locale, "/leaderboard")}?period=${nextPeriod}&control=${nextControl}`;
  }
  return (
    <div className="page-shell">
      <div className="section-heading">
        <p>PUBLIC LEDGER / LIVE API</p>
        <h1>
          One fleet.
          <br />
          One rank.
        </h1>
      </div>
      <div className="toolbar" aria-label={zh ? "排行榜筛选" : "Leaderboard filters"}>
        {["today", "week", "all"].map((value) => (
          <Link
            className="button button--small"
            data-active={period === value}
            href={filterLink(value, control)}
            key={value}
          >
            {value === "today"
              ? zh
                ? "今日"
                : "Today"
              : value === "week"
                ? zh
                  ? "本周"
                  : "This week"
                : zh
                  ? "历史"
                  : "All time"}
          </Link>
        ))}
        <span>/</span>
        {(humanPlayEnabled ? ["all", "human", "agent"] : ["all", "agent"]).map((value) => (
          <Link
            className="button button--small"
            data-active={control === value}
            href={filterLink(period, value)}
            key={value}
          >
            {value === "all"
              ? zh
                ? "全部控制"
                : "All control"
              : `${value.toUpperCase()} ${zh ? "标识" : "tag"}`}
          </Link>
        ))}
      </div>
      <p className="notice">
        {humanPlayEnabled
          ? zh
            ? "筛选只分析同一统一榜单中的参赛记录，不会创建 Human 榜或 Agent 榜。"
            : "Filters analyze records inside the same unified leaderboard; they never create separate Human or Agent rankings."
          : zh
            ? "当前版本只开放 Agent 自主比赛；所有正式结果进入同一舰队榜单。"
            : "This release exposes Agent-controlled matches only; every ranked result enters one fleet leaderboard."}
      </p>
      <div className="panel">
        {error && <p role="alert">{error}</p>}
        {!entries && !error && <p>{messages[locale].common.loading}</p>}
        {entries?.length === 0 && <p>{messages[locale].common.empty}</p>}
        {!!entries?.length && (
          <table className="rank-table">
            <thead>
              <tr>
                <th>RANK</th>
                <th>FLEET</th>
                <th>{zh ? "段位" : "DIVISION"}</th>
                <th>CONTROL TAGS</th>
                <th>{zh ? "战绩" : "RECORD"}</th>
                <th>{zh ? "总积分" : "TOTAL SCORE"}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.fleetPublicId}>
                  <td>{String(entry.rank).padStart(2, "0")}</td>
                  <td>
                    <Link href={localPath(locale, `/fleet/${entry.fleetPublicId}`)}>
                      {entry.name}
                      <small>{entry.commanderCode}</small>
                    </Link>
                  </td>
                  <td>
                    <span className="rank-division">
                      <strong>{competitiveRankLabel(locale, entry.competitiveRank)}</strong>
                      <small>{competitiveRankPoints(locale, entry.competitiveRank)}</small>
                    </span>
                  </td>
                  <td>
                    {entry.controlTags.map((tag) => (
                      <ModeTag key={tag} tone={tag}>
                        {tag.toUpperCase()}
                      </ModeTag>
                    ))}
                  </td>
                  <td>
                    {entry.record.wins}–{entry.record.losses}
                  </td>
                  <td className="mono">{formatNumber(locale, entry.displayScore)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function FleetProfileView({ locale, publicId }: { locale: Locale; publicId: string }) {
  const zh = locale === "zh";
  const [profile, setProfile] = useState<FleetProfile | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<FleetProfile>(`/api/public/v1/fleet-profiles/${publicId}`, {
      signal: controller.signal,
    })
      .then(setProfile)
      .catch((reason) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
      });
    return () => controller.abort();
  }, [locale, publicId]);
  if (!profile)
    return (
      <div className="page-shell">
        <section className="panel">
          <p role={error ? "alert" : undefined}>{error || messages[locale].common.loading}</p>
        </section>
      </div>
    );
  return (
    <div className="page-shell">
      <div className="section-heading">
        <p>PUBLIC FLEET / {profile.publicId.toUpperCase()}</p>
        <h1>{profile.name}</h1>
      </div>
      <div className="page-grid">
        <section className="panel">
          <p className="eyebrow">COMMANDER {profile.commanderCode}</p>
          <blockquote className="page-lede">
            “{profile.declaration || (zh ? "未公开宣言" : "No public declaration")}”
          </blockquote>
          <div className="status-list">
            <div className="status-row">
              <div>
                <strong>
                  {competitiveRankLabel(locale, profile.rating.competitiveRank)} · #
                  {profile.rating.rank ?? "—"}
                </strong>
                <p>
                  {zh ? "统一舰队排名" : "Unified fleet rank"} · {zh ? "总积分" : "total"}{" "}
                  {formatNumber(locale, profile.rating.displayScore)}
                </p>
              </div>
              <strong className="mono">
                {competitiveRankPoints(locale, profile.rating.competitiveRank)}
              </strong>
            </div>
            <div className="status-row">
              <div>
                <strong>
                  {profile.matches.length} {zh ? "场近期比赛" : "recent matches"}
                </strong>
                <p>{zh ? "来自公开 API" : "From the public API"}</p>
              </div>
              <div>
                {profile.controlTags.map((tag) => (
                  <ModeTag key={tag} tone={tag}>
                    {tag.toUpperCase()}
                  </ModeTag>
                ))}
              </div>
            </div>
          </div>
          <h2>{zh ? "近期战绩" : "Recent matches"}</h2>
          <div className="status-list">
            {profile.matches.map((match) => (
              <div className="status-row" key={match.publicId}>
                <div>
                  <strong>
                    {match.mode.toUpperCase()} · {match.status.toUpperCase()}
                  </strong>
                  <p>
                    {match.strategyVersionId ?? "manual"} · {formatDate(locale, match.createdAt)} ·{" "}
                    {match.publicId}
                  </p>
                </div>
                {match.replayPublicId ? (
                  <Link
                    className="button button--small"
                    href={localPath(locale, `/replay/${match.replayPublicId}`)}
                  >
                    {zh ? "回放" : "Replay"}
                  </Link>
                ) : (
                  <ModeTag tone={match.controllerType}>
                    {match.controllerType?.toUpperCase() ?? "—"}
                  </ModeTag>
                )}
              </div>
            ))}
          </div>
        </section>
        <aside className="panel">
          <p className="eyebrow">{zh ? "舰队事实" : "FLEET FACTS"}</p>
          <h2>{profile.strategyTendency}</h2>
          <p className="page-lede">{profile.styleDescription}</p>
          {profile.representativeReplayPublicId && (
            <Link
              className="button button--primary"
              href={localPath(locale, `/replay/${profile.representativeReplayPublicId}`)}
            >
              {zh ? "查看代表回放 →" : "Watch representative replay →"}
            </Link>
          )}
          <hr />
          <h3>{zh ? "版本谱系" : "Version lineage"}</h3>
          {profile.versions.map((version) => (
            <p className="mono" key={version.publicId}>
              {version.publicId} · {version.status.toUpperCase()} · {version.source}
            </p>
          ))}
        </aside>
      </div>
    </div>
  );
}

type HistoryMatch = {
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

function formatArtifactSize(locale: Locale, bytes: number): string {
  if (bytes < 1024) return `${formatNumber(locale, bytes)} B`;
  return `${new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en", { maximumFractionDigits: 1 }).format(bytes / 1024)} KB`;
}

export function HistoryView({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [matches, setMatches] = useState<HistoryMatch[] | null>(null);
  const [featured, setFeatured] = useState(false);
  const [control, setControl] = useState("all");
  const [error, setError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const query = `period=all&featured=${featured}${control === "all" ? "" : `&controller_type=${control}`}`;
    void apiFetchWithRetry<{ matches: HistoryMatch[] }>(
      `/api/public/v1/matches?${query}`,
      { signal: controller.signal },
      { attempts: 3 },
    )
      .then((value) => setMatches(value.matches))
      .catch((reason) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
      });
    return () => controller.abort();
  }, [control, featured, loadAttempt, locale]);
  return (
    <div className="page-shell">
      <div className="section-heading">
        <p>PUBLIC ENCOUNTERS / PERMANENT</p>
        <h1>
          {zh ? (
            <>
              真实对局。
              <br />
              可验证航迹。
            </>
          ) : (
            <>
              Real matches.
              <br />
              Verifiable traces.
            </>
          )}
        </h1>
      </div>
      <div className="toolbar">
        <button
          className="button button--small"
          data-active={featured}
          onClick={() => {
            setError("");
            setMatches(null);
            setFeatured((value) => !value);
          }}
          type="button"
        >
          {zh ? "精彩对局" : "Featured"}
        </button>
        {(humanPlayEnabled ? ["all", "human", "agent"] : ["all", "agent"]).map((value) => (
          <button
            className="button button--small"
            data-active={control === value}
            key={value}
            onClick={() => {
              setError("");
              setMatches(null);
              setControl(value);
            }}
            type="button"
          >
            {value === "all" ? (zh ? "全部控制" : "All control") : value.toUpperCase()}
          </button>
        ))}
      </div>
      {error && (
        <div className="history-error" role="alert">
          <span>{error}</span>
          <button
            className="button button--small"
            onClick={() => {
              setError("");
              setMatches(null);
              setLoadAttempt((value) => value + 1);
            }}
          >
            ↻ {messages[locale].common.retry}
          </button>
        </div>
      )}
      {!matches && !error && <p>{messages[locale].common.loading}</p>}
      {matches?.length === 0 && <p>{messages[locale].common.empty}</p>}
      <div className="status-list">
        {matches?.map((match) => {
          const winner = match.participants.find((item) => item.slot === match.result?.winnerSlot);
          return (
            <article className="panel" key={match.publicId}>
              <div className="status-row">
                <div>
                  <p className="eyebrow">
                    EPISODE / {match.publicId} · {match.mode.toUpperCase()}
                  </p>
                  <h2>{match.participants.map((item) => item.fleetName).join(" / ")}</h2>
                  <p>
                    {zh ? "胜方" : "Winner"}: {winner?.fleetName ?? (zh ? "平局" : "Draw")} ·{" "}
                    {match.result?.reason ?? "—"}
                  </p>
                </div>
                <Link
                  className="button button--primary"
                  href={localPath(locale, `/replay/${match.replayPublicId}`)}
                >
                  {zh ? "永久回放 →" : "Permanent replay →"}
                </Link>
              </div>
              <div className="history-artifact-meta">
                <span>
                  <small>{zh ? "地图" : "MAP"}</small>
                  <strong>{match.mapId}</strong>
                </span>
                <span>
                  <small>{zh ? "回放工件" : "REPLAY ARTIFACT"}</small>
                  <strong>
                    V{match.replayArtifact.schemaVersion} · {match.replayArtifact.frameCount}{" "}
                    {zh ? "帧" : "FRAMES"} ·{" "}
                    {formatArtifactSize(locale, match.replayArtifact.sizeBytes)}
                  </strong>
                </span>
                <span>
                  <small>{zh ? "已保存" : "SAVED"}</small>
                  <strong>{formatDate(locale, match.replayArtifact.savedAt)}</strong>
                </span>
              </div>
              <div className="history-participants">
                {match.participants.map((item) => (
                  <span key={item.slot}>
                    <ModeTag tone={item.controllerType}>
                      {item.controllerType.toUpperCase()}
                    </ModeTag>{" "}
                    {item.strategyVersionId ?? "manual"}{" "}
                    {item.submittedBy ? `· ${item.submittedBy}` : ""}{" "}
                    {typeof item.ratingChange?.delta === "number"
                      ? `· ${formatRatingDelta(item.ratingChange.delta)}`
                      : ""}{" "}
                  </span>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
