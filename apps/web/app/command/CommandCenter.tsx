"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch, type AgentKey, type Fleet, type FleetProfile } from "../../src/api";
import {
  errorMessage,
  formatDate,
  formatNumber,
  localPath,
  messages,
  type Locale,
} from "../../src/i18n";
import { competitiveRankLabel, competitiveRankPoints } from "../../src/rating";
import { humanPlayEnabled } from "../../src/features";

const scopes = [
  "fleet:read",
  "version:read",
  "version:write",
  "matches:read",
  "opponents:read",
  "simulate",
  "challenge",
];

export function CommandCenter({ locale = "zh" }: { locale?: Locale }) {
  const zh = locale === "zh";
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [profile, setProfile] = useState<FleetProfile | null>(null);
  const [keys, setKeys] = useState<AgentKey[]>([]);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const owned = await apiFetch<Fleet>("/api/v1/me/fleet");
      const [publicProfile, agentKeys] = await Promise.all([
        apiFetch<FleetProfile>(`/api/public/v1/fleet-profiles/${owned.publicId}`),
        apiFetch<AgentKey[]>(`/api/v1/fleets/${owned.publicId}/agent-keys`),
      ]);
      setFleet(owned);
      setProfile(publicProfile);
      setKeys(agentKeys);
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    }
  }, [locale]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createKey() {
    if (!fleet) return;
    setBusy(true);
    try {
      const created = await apiFetch<{ key: string }>(
        `/api/v1/fleets/${fleet.publicId}/agent-keys`,
        {
          body: JSON.stringify({ scopes }),
          method: "POST",
        },
      );
      setSecret(created.key);
      await load();
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    } finally {
      setBusy(false);
    }
  }

  async function revokeKey(publicPrefix: string) {
    if (!fleet) return;
    setBusy(true);
    try {
      await apiFetch<void>(`/api/v1/fleets/${fleet.publicId}/agent-keys/${publicPrefix}`, {
        method: "DELETE",
      });
      setSecret(null);
      await load();
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    } finally {
      setBusy(false);
    }
  }

  async function selectVersion(publicId: string) {
    if (!fleet) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/fleets/${fleet.publicId}/current-strategy`, {
        body: JSON.stringify({ strategyVersionId: publicId }),
        method: "PATCH",
      });
      await load();
    } catch (reason) {
      setError(errorMessage(locale, reason instanceof ApiError ? reason.code : undefined));
    } finally {
      setBusy(false);
    }
  }

  if (!fleet || !profile) {
    return (
      <div className="page-shell">
        <section className="panel">
          <p role={error ? "alert" : undefined}>{error || messages[locale].common.loading}</p>
          {error.includes(zh ? "尚未" : "not established") && (
            <Link className="button button--primary" href={localPath(locale, "/start")}>
              {zh ? "创建舰队" : "Create fleet"}
            </Link>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <div className="section-heading">
        <p>COMMAND DOSSIER / {fleet.publicId.toUpperCase()}</p>
        <h1>{fleet.name}</h1>
      </div>
      {error && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}
      <section className="mission-cta" aria-labelledby="next-mission-title">
        <span className="mission-cta__index">
          NEXT
          <br />
          01
        </span>
        <div>
          <p className="eyebrow">READY FOR CONTACT</p>
          <h2 id="next-mission-title">
            {zh
              ? humanPlayEnabled
                ? "舰队已就位。现在开一把。"
                : "舰队已就位。让 Agent 出战。"
              : humanPlayEnabled
                ? "Your fleet is ready. Start a match."
                : "Your fleet is ready. Deploy the Agent."}
          </h2>
          <p>
            {humanPlayEnabled
              ? zh
                ? "默认是训练赛，不影响排名。选择 Human 亲自操作，或让当前 Agent 策略执行。"
                : "Training is the default and does not affect rating. Command as Human or run the current Agent strategy."
              : zh
                ? "默认是训练赛，不影响排名。比赛会锁定当前 ready 策略并由 Agent 自主执行。"
                : "Training is the default and does not affect rating. The match locks the current ready strategy and runs autonomously."}
          </p>
        </div>
        <div className="mission-cta__actions">
          {humanPlayEnabled && (
            <Link className="button" href={`${localPath(locale, "/arena")}?control=human`}>
              {zh ? "我来操作" : "Command it"}
            </Link>
          )}
          <Link
            className="button button--primary"
            href={`${localPath(locale, "/arena")}?control=agent`}
          >
            {zh ? "让 Agent 出战 →" : "Deploy Agent →"}
          </Link>
        </div>
      </section>
      <div className="page-grid">
        <section className="panel">
          <p className="eyebrow">UNIFIED RATING</p>
          <div className="status-row">
            <div>
              <strong>
                {competitiveRankLabel(locale, profile.rating.competitiveRank)} · #
                {profile.rating.rank ?? "—"}
              </strong>
              <p>
                {humanPlayEnabled
                  ? zh
                    ? "Human + Agent 正式战共用此分数"
                    : "One score for all Human + Agent ranked matches"
                  : zh
                    ? "所有 Agent 正式战共用舰队唯一分数"
                    : "One fleet score across every ranked Agent match"}{" "}
                · {zh ? "总积分" : "total"} {formatNumber(locale, profile.rating.displayScore)}
              </p>
            </div>
            <strong className="mono">
              {competitiveRankPoints(locale, profile.rating.competitiveRank)}
            </strong>
          </div>
          <h2>{zh ? "策略版本" : "Strategy versions"}</h2>
          <div className="status-list">
            {profile.versions.map((version) => (
              <div className="status-row" key={version.publicId}>
                <div>
                  <strong>{version.notes || version.publicId}</strong>
                  <p>
                    {version.publicId} · {formatDate(locale, version.createdAt)} ·{" "}
                    {version.status.toUpperCase()} · {version.source}
                  </p>
                </div>
                {fleet.currentStrategyVersionId === version.publicId ? (
                  <span className="mode-tag" data-tone="agent">
                    CURRENT
                  </span>
                ) : (
                  <button
                    className="button button--small"
                    disabled={busy || version.status !== "ready"}
                    onClick={() => void selectVersion(version.publicId)}
                    type="button"
                  >
                    {zh ? "设为当前" : "Set current"}
                  </button>
                )}
              </div>
            ))}
          </div>
          <p className="notice">
            {zh
              ? "切换只移动当前版本指针；历史比赛保留开赛时锁定的版本。"
              : "Switching only moves the current pointer; past matches keep their locked attribution."}
          </p>
        </section>
        <aside className="panel">
          <p className="eyebrow">AGENT ACCESS</p>
          <h2>Agent Key</h2>
          <p className="page-lede">
            {zh
              ? "密钥明文只在生成时出现一次，平台只保存摘要。"
              : "The secret appears once. The platform stores only its digest."}
          </p>
          {secret && (
            <div role="status">
              <p className="notice">
                {zh ? "现在复制；离开后无法再次查看。" : "Copy it now; it cannot be shown again."}
              </p>
              <p className="secret">{secret}</p>
              <button
                className="button button--small"
                onClick={() => void navigator.clipboard.writeText(secret)}
                type="button"
              >
                {zh ? "复制密钥" : "Copy key"}
              </button>
            </div>
          )}
          <div className="status-list">
            {keys.map((key) => (
              <div className="status-row" key={key.publicPrefix}>
                <div>
                  <strong>owk_{key.publicPrefix}_••••</strong>
                  <p>{key.scopes.join(" · ")}</p>
                </div>
                {key.active ? (
                  <button
                    className="button button--danger button--small"
                    disabled={busy}
                    onClick={() => void revokeKey(key.publicPrefix)}
                    type="button"
                  >
                    {zh ? "撤销" : "Revoke"}
                  </button>
                ) : (
                  <span>REVOKED</span>
                )}
              </div>
            ))}
          </div>
          {!keys.length && <p>{messages[locale].common.empty}</p>}
          <button
            className="button button--primary"
            disabled={busy}
            onClick={() => void createKey()}
            type="button"
          >
            {zh ? "生成新 Key" : "Generate key"}
          </button>
          <hr />
          <Link className="button" href={localPath(locale, "/agent-guide")}>
            {zh ? "打开 Agent Guide →" : "Open Agent Guide →"}
          </Link>
        </aside>
      </div>
    </div>
  );
}
