"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { buildAgentHandoffBundle, resolveCommandMission } from "../../src/agent-handoff";
import {
  ApiError,
  apiFetch,
  apiUrl,
  type AgentKey,
  type Fleet,
  type FleetProfile,
} from "../../src/api";
import { writeClipboard } from "../../src/clipboard";
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
  const [copyState, setCopyState] = useState<"bundle" | "key" | "error" | null>(null);

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

  useEffect(() => {
    if (!copyState) return;
    const timer = window.setTimeout(() => setCopyState(null), 2400);
    return () => window.clearTimeout(timer);
  }, [copyState]);

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

  async function copyAgentAccess(target: "bundle" | "key") {
    if (!secret || !fleet) return;
    const text =
      target === "key"
        ? secret
        : buildAgentHandoffBundle({
            locale,
            key: secret,
            fleetId: fleet.publicId,
            apiBaseUrl: apiUrl("/api/agent/v1", window.location.origin),
            guideUrl: new URL(localPath(locale, "/agent-guide"), window.location.origin).toString(),
          });
    try {
      await writeClipboard(text);
      setCopyState(target);
    } catch {
      setCopyState("error");
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

  const currentVersion = profile.versions.find(
    (version) => version.publicId === fleet.currentStrategyVersionId,
  );
  const mission = resolveCommandMission({
    secret,
    hasActiveKey: keys.some((key) => key.active),
    currentStrategyStatus: currentVersion?.status ?? null,
  });
  const missionCopy = {
    "copy-handoff": {
      eyebrow: "ONE-TIME UPLINK",
      title: zh
        ? "密钥已生成。现在把接入包交给 Agent。"
        : "Key generated. Hand the uplink to your Agent.",
      body: zh
        ? "一次复制 API 地址、接入指南、舰队 ID、密钥和安全的首条任务。离开页面后无法再次查看该密钥。"
        : "Copy the API address, guide, fleet ID, key, and a safe first mission in one action. The key cannot be shown again after you leave.",
    },
    "needs-agent-key": {
      eyebrow: "AGENT ACCESS REQUIRED",
      title: zh ? "先生成 Agent Key。" : "Generate an Agent Key first.",
      body: zh
        ? "这是 Agent 调用舰队、版本、对手和比赛 API 的唯一凭证；明文只展示一次。"
        : "This is the Agent's credential for fleet, version, opponent, and match APIs. Its plaintext is shown once.",
    },
    "needs-ready-strategy": {
      eyebrow: "STRATEGY REQUIRED",
      title: zh ? "选择一个 ready 策略。" : "Select a ready strategy.",
      body: zh
        ? "比赛只会锁定当前 ready 版本。请在下方版本列表中选择，或先按接入指南上传新版本。"
        : "Matches lock the current ready version. Select one below, or follow the guide to upload a new version.",
    },
    "battle-ready": {
      eyebrow: "READY FOR CONTACT",
      title: zh ? "接入完成。让 Agent 出战。" : "Uplink ready. Deploy the Agent.",
      body: zh
        ? "默认从训练赛开始，不影响排名；确认表现后再切换到正式排位。"
        : "Start with training so rating is unaffected, then move to ranked play after verifying performance.",
    },
  }[mission];

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
      <section className="mission-cta" data-state={mission} aria-labelledby="next-mission-title">
        <span className="mission-cta__index">
          NEXT
          <br />
          01
        </span>
        <div>
          <p className="eyebrow">{missionCopy.eyebrow}</p>
          <h2 id="next-mission-title">{missionCopy.title}</h2>
          <p>{missionCopy.body}</p>
        </div>
        <div className="mission-cta__actions" aria-live="polite">
          {mission === "copy-handoff" && (
            <button
              className="button button--primary"
              onClick={() => void copyAgentAccess("bundle")}
              type="button"
            >
              {copyState === "bundle"
                ? zh
                  ? "接入包已复制"
                  : "Handoff copied"
                : copyState === "error"
                  ? zh
                    ? "复制失败，请重试"
                    : "Copy failed — retry"
                  : zh
                    ? "复制完整接入包 →"
                    : "Copy full handoff →"}
            </button>
          )}
          {mission === "needs-agent-key" && (
            <button
              className="button button--primary"
              disabled={busy}
              onClick={() => void createKey()}
              type="button"
            >
              {zh ? "生成一次性 Key →" : "Generate one-time key →"}
            </button>
          )}
          {mission === "needs-ready-strategy" && (
            <a className="button button--primary" href="#strategy-versions">
              {zh ? "查看策略版本 ↓" : "Review strategy versions ↓"}
            </a>
          )}
          {mission === "battle-ready" && (
            <Link
              className="button button--primary"
              href={`${localPath(locale, "/arena")}?control=agent`}
            >
              {zh ? "让 Agent 出战 →" : "Deploy Agent →"}
            </Link>
          )}
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
          <h2 id="strategy-versions">{zh ? "策略版本" : "Strategy versions"}</h2>
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
                onClick={() => void copyAgentAccess("key")}
                type="button"
              >
                {copyState === "key"
                  ? zh
                    ? "密钥已复制"
                    : "Key copied"
                  : zh
                    ? "仅复制密钥"
                    : "Copy key only"}
              </button>
              <button
                className="button button--primary button--small"
                onClick={() => void copyAgentAccess("bundle")}
                type="button"
              >
                {copyState === "bundle"
                  ? zh
                    ? "接入包已复制"
                    : "Handoff copied"
                  : zh
                    ? "复制完整接入包"
                    : "Copy full handoff"}
              </button>
              {copyState === "error" && (
                <p className="notice notice--error">
                  {zh ? "复制失败，请重试。" : "Copy failed. Please retry."}
                </p>
              )}
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
