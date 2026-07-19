"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError, apiFetchWithRetry, type MatchStatusRecord } from "../../src/api";
import { errorMessage, formatDate, localPath, type Locale } from "../../src/i18n";
import { matchModeName, replayReasonName } from "../../src/public-replay";

const activeStatuses = new Set(["queued", "preparing", "ready", "running", "finalizing"]);

function statusCopy(locale: Locale, match: MatchStatusRecord): [string, string] {
  const zh = locale === "zh";
  if (match.status === "finished" && match.replayPublicId)
    return zh
      ? ["比赛已完成", "权威回放已经就绪。"]
      : ["Match complete", "The authoritative replay is ready."];
  if (match.status === "finished")
    return zh
      ? ["比赛已完成", "正在生成回放，页面会继续更新。"]
      : ["Match complete", "Replay processing; this page will keep updating."];
  if (["failed", "forfeited", "cancelled"].includes(match.status))
    return zh
      ? ["比赛未完成", "本场已经结束，可返回竞技场重新开始。"]
      : ["Match did not complete", "This run ended. Return to Arena to try again."];
  if (["running", "ready"].includes(match.status))
    return zh
      ? ["比赛进行中", "双方策略正在权威服务器上执行。"]
      : ["Match in progress", "Both strategies are executing on the authoritative server."];
  if (["preparing", "finalizing"].includes(match.status))
    return zh
      ? ["正在处理比赛", "服务器正在准备或整理权威结果。"]
      : ["Processing match", "The server is preparing or finalizing the authoritative result."];
  return zh
    ? ["比赛已进入队列", "等待可用执行资源。"]
    : ["Match queued", "Waiting for an available execution slot."];
}

export function MatchStatusView({ locale, matchId }: { locale: Locale; matchId: string }) {
  const zh = locale === "zh";
  const [match, setMatch] = useState<MatchStatusRecord | null>(null);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    async function poll() {
      try {
        const value = await apiFetchWithRetry<MatchStatusRecord>(
          `/api/v1/matches/${encodeURIComponent(matchId)}`,
          { signal: controller.signal },
          { attempts: 2, baseDelayMs: 250 },
        );
        setMatch(value);
        setError("");
        setLastUpdated(new Date());
        if (
          activeStatuses.has(value.status) ||
          (value.status === "finished" && !value.replayPublicId)
        ) {
          timer = window.setTimeout(() => void poll(), 2000);
        }
      } catch (reason) {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
        timer = window.setTimeout(() => void poll(), 4000);
      }
    }
    void poll();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [locale, matchId, retryKey]);

  const copy = match ? statusCopy(locale, match) : null;
  const winner = useMemo(
    () => match?.participants.find((participant) => participant.slot === match.result?.winnerSlot),
    [match],
  );

  return (
    <section className="match-status panel" aria-live="polite">
      <div className="match-status__heading">
        <div>
          <p className="eyebrow">MATCH STATUS / {matchId}</p>
          <h1>{copy?.[0] ?? (zh ? "正在读取比赛状态…" : "Loading match status…")}</h1>
          <p className="page-lede">{copy?.[1]}</p>
        </div>
        {match && (
          <div className="match-status__signal" data-status={match.status}>
            <span>{matchModeName(locale, match.mode)}</span>
            <strong>{match.status.toUpperCase()}</strong>
            <small>
              {lastUpdated
                ? `${zh ? "最近更新" : "Updated"} ${lastUpdated.toLocaleTimeString()}`
                : "—"}
            </small>
          </div>
        )}
      </div>

      {match && (
        <div className="match-status__versus">
          {match.participants.map((participant) => (
            <div key={participant.slot}>
              <span>{String(participant.slot + 1).padStart(2, "0")}</span>
              <strong>{participant.fleetName}</strong>
              <small>{participant.controllerType.toUpperCase()}</small>
            </div>
          ))}
        </div>
      )}

      {match?.status === "finished" && (
        <p className="notice">
          {winner
            ? zh
              ? `${winner.fleetName} 获胜 · ${replayReasonName(locale, match.result?.reason)}`
              : `${winner.fleetName} wins · ${replayReasonName(locale, match.result?.reason)}`
            : zh
              ? "本场战平。"
              : "This match ended in a draw."}
        </p>
      )}

      {error && (
        <div className="history-error" role="alert">
          <span>{error}</span>
          <button
            className="button button--small"
            onClick={() => setRetryKey((value) => value + 1)}
          >
            ↻ {zh ? "立即重试" : "Retry now"}
          </button>
        </div>
      )}

      <div className="toolbar">
        {match?.replayPublicId && (
          <Link
            className="button button--primary"
            href={localPath(locale, `/replay/${match.replayPublicId}`)}
          >
            {zh ? "查看回放 →" : "Watch replay →"}
          </Link>
        )}
        <Link className="button" href={localPath(locale, "/arena")}>
          {match && ["failed", "forfeited", "cancelled"].includes(match.status)
            ? zh
              ? "返回竞技场再开一局"
              : "Return to Arena and try again"
            : zh
              ? "返回竞技场"
              : "Back to Arena"}
        </Link>
        {match?.createdAt && (
          <small>
            {zh ? "创建于" : "Created"} {formatDate(locale, match.createdAt)}
          </small>
        )}
      </div>
    </section>
  );
}
