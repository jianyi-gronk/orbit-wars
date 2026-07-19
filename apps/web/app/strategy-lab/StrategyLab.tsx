"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  apiFetch,
  idempotencyKey,
  type AiAssist,
  type Fleet,
  type LabSimulation,
  type StrategyLabWorkspace,
} from "../../src/api";
import { formatDate, localPath, type Locale } from "../../src/i18n";
import {
  matchModeName,
  replayEventName,
  replayReasonName,
  type CompactReplay,
} from "../../src/public-replay";

type AssistKind = "explain" | "suggest" | "patch";

function labError(locale: Locale, reason: unknown): string {
  const zh = locale === "zh";
  const code = reason instanceof ApiError ? reason.code : "unknown";
  const labels: Record<string, [string, string]> = {
    "strategy_lab.revision_conflict": [
      "草稿已在另一个页面更新，请重新载入。",
      "The draft changed elsewhere. Reload before continuing.",
    ],
    "strategy_lab.not_validated": [
      "当前草稿还没有通过模拟验证。",
      "The current draft has not passed simulation validation.",
    ],
    "strategy_lab.simulation_required": [
      "请先运行当前草稿的策略模拟。",
      "Run a strategy simulation for the current draft first.",
    ],
    "strategy_lab.simulation_pending": [
      "策略模拟尚未完成，请等待权威结果。",
      "The strategy simulation has not completed yet.",
    ],
    "strategy_lab.simulation_failed": [
      "策略模拟未成功完成，请重新运行。",
      "The strategy simulation did not complete successfully. Run it again.",
    ],
    "strategy_lab.simulation_stale": [
      "草稿已经变化，请为当前版本重新运行模拟。",
      "The draft changed. Run a new simulation for this revision.",
    ],
    "strategy_lab.simulation_not_passed": [
      "模拟完成，但当前候选没有通过验证。",
      "The simulation completed, but this candidate did not pass validation.",
    ],
    "strategy_lab.validation_unavailable": [
      "验证环境暂时不可用，草稿仍已保存。",
      "Validation is temporarily unavailable. Your draft is still saved.",
    ],
    "ai.unavailable": [
      "AI 副驾暂时不可用，你仍可手动编辑和模拟。",
      "AI assistance is unavailable. Manual editing and simulation still work.",
    ],
    "ai.quota_exhausted": [
      "免费 AI 额度已用完，手动功能不受影响。",
      "Free AI credits are exhausted. Manual tools remain available.",
    ],
    "ai.rate_limited": [
      "AI 请求过于频繁，请稍后再试。",
      "AI requests are rate-limited. Try again later.",
    ],
    "ai.consent_required": [
      "请先确认本次发送给 DeepSeek 的数据范围。",
      "Confirm the data sent to DeepSeek before continuing.",
    ],
  };
  return (
    labels[code]?.[zh ? 0 : 1] ??
    (zh ? "操作未完成，请稍后重试。" : "Action failed. Try again shortly.")
  );
}

export function StrategyLab({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const searchParams = useSearchParams();
  const fromReplay = searchParams.get("fromReplay");
  const [workspace, setWorkspace] = useState<StrategyLabWorkspace | null>(null);
  const [source, setSource] = useState("");
  const [mode, setMode] = useState<"guided" | "code">("guided");
  const [parameters, setParameters] = useState<StrategyLabWorkspace["draft"]["parameters"]>({});
  const [fleetMissing, setFleetMissing] = useState(false);
  const [busy, setBusy] = useState<"save" | "simulate" | "publish" | "ai" | "version" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [simulation, setSimulation] = useState<LabSimulation | null>(null);
  const [sourceReplay, setSourceReplay] = useState<CompactReplay | null>(null);
  const [sourceUnavailable, setSourceUnavailable] = useState(false);
  const [simulationRefreshError, setSimulationRefreshError] = useState("");
  const [simulationRefreshKey, setSimulationRefreshKey] = useState(0);
  const [assist, setAssist] = useState<AiAssist | null>(null);
  const [assistKind, setAssistKind] = useState<AssistKind>("suggest");
  const [assistGoal, setAssistGoal] = useState("");
  const [deep, setDeep] = useState(false);
  const [consent, setConsent] = useState(false);

  const sync = useCallback((value: StrategyLabWorkspace) => {
    setWorkspace(value);
    setSource(value.draft.sourceCode);
    setMode(value.draft.mode);
    setParameters(value.draft.parameters);
    setSimulation(value.simulation);
    setDirty(false);
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      const fleet = await apiFetch<Fleet>("/api/v1/me/fleet");
      sync(await apiFetch<StrategyLabWorkspace>(`/api/v1/fleets/${fleet.publicId}/strategy-lab`));
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "fleet.not_found") setFleetMissing(true);
      else setError(labError(locale, reason));
    }
  }, [locale, sync]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const active = new Set(["queued", "preparing", "ready", "running", "finalizing"]);
    if (!workspace?.simulation || !active.has(workspace.simulation.status)) return;
    const controller = new AbortController();
    let timer = window.setTimeout(async () => {
      try {
        const latest = await apiFetch<StrategyLabWorkspace>(
          `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab`,
          { signal: controller.signal },
        );
        setWorkspace(latest);
        setSimulation(latest.simulation);
        setSimulationRefreshError("");
      } catch (reason) {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setSimulationRefreshError(
          zh
            ? "暂时无法更新模拟状态，页面会自动重试。"
            : "Simulation status is temporarily unavailable. This page will retry.",
        );
        timer = window.setTimeout(() => setSimulationRefreshKey((value) => value + 1), 4000);
      }
    }, 2000);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [simulationRefreshKey, workspace?.fleet.publicId, workspace?.simulation, zh]);

  useEffect(() => {
    const controller = new AbortController();
    if (!fromReplay) return () => controller.abort();
    void apiFetch<CompactReplay>(
      `/api/public/v1/replays/${encodeURIComponent(fromReplay)}/compact`,
      { signal: controller.signal },
    )
      .then((value) => {
        setSourceReplay(value);
        setSourceUnavailable(false);
      })
      .catch((reason) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setSourceReplay(null);
        setSourceUnavailable(true);
      });
    return () => controller.abort();
  }, [fromReplay]);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  const currentVersion = useMemo(
    () =>
      workspace?.versions.find(
        (version) => version.publicId === workspace.fleet.currentStrategyVersionId,
      ),
    [workspace],
  );

  const sourceHighlight = useMemo(() => {
    if (!sourceReplay) return null;
    const event = sourceReplay.events[0];
    if (event)
      return `${replayEventName(locale, event.type)} · ${zh ? "第" : "Step "}${event.step}${zh ? "步" : ""}`;
    const facts = Array.isArray(sourceReplay.facts)
      ? sourceReplay.facts
      : sourceReplay.facts
        ? [sourceReplay.facts]
        : [];
    return facts[0] ?? replayReasonName(locale, sourceReplay.result?.reason);
  }, [locale, sourceReplay, zh]);

  function publishBlockReason(): string {
    if (dirty) return zh ? "请先保存当前草稿。" : "Save the current draft first.";
    const reason = workspace?.publishEligibility.blockingReason;
    const labels: Record<string, [string, string]> = {
      simulation_required: ["请先运行策略模拟。", "Run a strategy simulation first."],
      simulation_pending: ["等待策略模拟完成。", "Waiting for the strategy simulation."],
      simulation_failed: ["模拟失败，请重新运行。", "Simulation failed. Run it again."],
      simulation_stale: ["草稿已变化，请重新模拟。", "Draft changed. Run a new simulation."],
      simulation_not_passed: [
        "验证未通过，请调整后重试。",
        "Validation did not pass. Revise and retry.",
      ],
      simulation_unknown: [
        "无法确认模拟状态，请刷新重试。",
        "Simulation status is unknown. Refresh and retry.",
      ],
    };
    return reason
      ? (labels[reason]?.[zh ? 0 : 1] ?? (zh ? "当前不可发布。" : "Publishing is locked."))
      : "";
  }

  function chooseMode(next: "guided" | "code") {
    if (
      next === "guided" &&
      mode === "code" &&
      !source.includes("Generated by Orbit/Wars Strategy Lab")
    ) {
      setNotice(
        zh
          ? "自定义代码无法无损转换为调参模式；可继续编辑，或重置为平台模板。"
          : "Custom code cannot safely convert to Guided mode. Keep editing or reset the template.",
      );
      return;
    }
    setMode(next);
    setDirty(true);
    setNotice("");
  }

  async function saveDraft(): Promise<boolean> {
    if (!workspace) return false;
    setBusy("save");
    setError("");
    try {
      const next = await apiFetch<StrategyLabWorkspace>(
        `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab/draft`,
        {
          method: "PUT",
          body: JSON.stringify({
            expectedRevision: workspace.draft.revision,
            mode,
            sourceCode: source,
            parameters,
          }),
        },
      );
      sync(next);
      setNotice(zh ? "草稿已安全保存。" : "Draft saved safely.");
      return true;
    } catch (reason) {
      setError(labError(locale, reason));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function resetTemplate() {
    if (!workspace) return;
    setBusy("save");
    setError("");
    try {
      const next = await apiFetch<StrategyLabWorkspace>(
        `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab/reset`,
        {
          method: "POST",
          body: JSON.stringify({ expectedRevision: workspace.draft.revision }),
        },
      );
      sync(next);
      setAssist(null);
      setNotice(zh ? "已重置为可编辑的平台基础模板。" : "Reset to the editable platform template.");
    } catch (reason) {
      setError(labError(locale, reason));
    } finally {
      setBusy(null);
    }
  }

  async function simulate() {
    if (!workspace) return;
    const hadUnsavedChanges = dirty;
    if (hadUnsavedChanges && !(await saveDraft())) return;
    setBusy("simulate");
    setError("");
    try {
      const latest = hadUnsavedChanges
        ? await apiFetch<StrategyLabWorkspace>(
            `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab`,
          )
        : workspace;
      const created = await apiFetch<LabSimulation>(
        `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab/simulations`,
        {
          method: "POST",
          body: JSON.stringify({
            revision: latest.draft.revision,
            opponentId: "training-v1",
            idempotencyKey: idempotencyKey("strategy-lab-sim"),
          }),
        },
      );
      setSimulation(created);
      sync(
        await apiFetch<StrategyLabWorkspace>(
          `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab`,
        ),
      );
      setNotice(
        zh
          ? "候选已通过固定验证，训练模拟已进入队列。"
          : "Candidate validated; training simulation queued.",
      );
    } catch (reason) {
      setError(labError(locale, reason));
    } finally {
      setBusy(null);
    }
  }

  async function askAi() {
    if (!workspace) return;
    setBusy("ai");
    setError("");
    try {
      const result = await apiFetch<AiAssist>(
        `/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab/ai-assists`,
        {
          method: "POST",
          body: JSON.stringify({
            revision: workspace.draft.revision,
            kind: assistKind,
            deep,
            consent,
            goal: assistGoal,
          }),
        },
      );
      setAssist(result);
      setWorkspace({
        ...workspace,
        aiCredits: { ...workspace.aiCredits, remaining: result.remaining },
      });
    } catch (reason) {
      setError(labError(locale, reason));
    } finally {
      setBusy(null);
    }
  }

  function acceptPatch() {
    if (!assist) return;
    setSource(assist.proposedSource);
    setMode("code");
    setDirty(true);
    setNotice(
      zh
        ? "补丁已放入私有草稿，尚未保存或发布。"
        : "Patch placed in the private draft; not saved or published yet.",
    );
  }

  async function publish() {
    if (!workspace) return;
    setBusy("publish");
    setError("");
    try {
      await apiFetch(`/api/v1/fleets/${workspace.fleet.publicId}/strategy-lab/publish`, {
        method: "POST",
        body: JSON.stringify({
          revision: workspace.draft.revision,
          notes: zh ? "由站内策略实验室发布" : "Published from Strategy Lab",
          makeCurrent: true,
        }),
      });
      await load();
      setNotice(
        zh
          ? "新版本已验证、发布并设为当前。"
          : "New version validated, published, and set current.",
      );
    } catch (reason) {
      setError(labError(locale, reason));
    } finally {
      setBusy(null);
    }
  }

  async function selectVersion(publicId: string) {
    if (!workspace) return;
    setBusy("version");
    try {
      await apiFetch(`/api/v1/fleets/${workspace.fleet.publicId}/current-strategy`, {
        method: "PATCH",
        body: JSON.stringify({ strategyVersionId: publicId }),
      });
      await load();
      setNotice(zh ? "当前出战版本已切换。" : "Current battle version changed.");
    } catch (reason) {
      setError(labError(locale, reason));
    } finally {
      setBusy(null);
    }
  }

  if (fleetMissing)
    return (
      <section className="panel strategy-lab-empty">
        <p className="eyebrow">STRATEGY LAB / NO FLEET</p>
        <h2>{zh ? "先建立舰队，再开始迭代。" : "Establish a fleet before iterating."}</h2>
        <Link className="button button--primary" href={localPath(locale, "/start")}>
          {zh ? "创建舰队 →" : "Create fleet →"}
        </Link>
      </section>
    );

  if (!workspace)
    return (
      <section className="panel">
        {error || (zh ? "正在载入策略草稿…" : "Loading strategy draft…")}
      </section>
    );

  return (
    <div className="strategy-lab">
      <header className="strategy-lab__header">
        <div>
          <p className="eyebrow">PRIVATE WORKSPACE / REV {workspace.draft.revision}</p>
          <h1>
            {zh ? `${workspace.fleet.name} 策略实验室` : `${workspace.fleet.name} Strategy Lab`}
          </h1>
          <p>
            {zh
              ? "草稿默认私有。先模拟验证，再发布为不可变版本。"
              : "Drafts stay private. Simulate first, then publish an immutable version."}
          </p>
        </div>
        <div className="strategy-lab__current">
          <span>{zh ? "当前出战版本" : "CURRENT BATTLE VERSION"}</span>
          <strong>{currentVersion?.notes || currentVersion?.publicId || "—"}</strong>
          <small>{currentVersion?.status.toUpperCase() || "NO READY VERSION"}</small>
        </div>
      </header>

      {sourceReplay && fromReplay && (
        <section className="panel strategy-source-card">
          <div>
            <p className="eyebrow">FROM REPLAY / {matchModeName(locale, sourceReplay.mode)}</p>
            <h2>
              {sourceReplay.participants
                .map((participant) => participant.fleetName ?? "—")
                .join(" vs ")}
            </h2>
            <p>
              {sourceReplay.result?.winnerSlot == null
                ? zh
                  ? "战果：平局"
                  : "Result: draw"
                : zh
                  ? `战果：${sourceReplay.participants.find((participant) => participant.slot === sourceReplay.result?.winnerSlot)?.fleetName ?? "未知舰队"} 获胜`
                  : `Result: ${sourceReplay.participants.find((participant) => participant.slot === sourceReplay.result?.winnerSlot)?.fleetName ?? "Unknown fleet"} won`}
              {sourceHighlight ? ` · ${sourceHighlight}` : ""}
            </p>
          </div>
          <Link className="button" href={localPath(locale, `/replay/${fromReplay}`)}>
            {zh ? "返回回放" : "Back to replay"}
          </Link>
        </section>
      )}
      {sourceUnavailable && (
        <p className="notice" role="status">
          {zh
            ? "来源回放不可用；你仍可继续编辑当前策略。"
            : "The source replay is unavailable. You can still edit this strategy."}
        </p>
      )}

      {(error || notice) && (
        <p className={`notice ${error ? "notice--error" : ""}`} role={error ? "alert" : "status"}>
          {error || notice}
        </p>
      )}

      <section className="strategy-lab__workspace">
        <div className="strategy-editor">
          <div className="strategy-editor__toolbar">
            <div role="group" aria-label={zh ? "编辑模式" : "Editing mode"}>
              <button
                aria-pressed={mode === "guided"}
                onClick={() => chooseMode("guided")}
                type="button"
              >
                {zh ? "策略调参" : "Guided"}
              </button>
              <button
                aria-pressed={mode === "code"}
                onClick={() => chooseMode("code")}
                type="button"
              >
                {zh ? "代码模式" : "Code"}
              </button>
            </div>
            <span>{dirty ? (zh ? "未保存" : "UNSAVED") : zh ? "已保存" : "SAVED"}</span>
          </div>

          {mode === "guided" ? (
            <div className="strategy-guided">
              <label>
                <span>{zh ? "出击比例" : "Launch ratio"}</span>
                <output>{Math.round(Number(parameters.launchRatio ?? 0.35) * 100)}%</output>
                <input
                  type="range"
                  min="0.1"
                  max="0.9"
                  step="0.05"
                  value={parameters.launchRatio ?? 0.35}
                  onChange={(event) => {
                    setParameters({ ...parameters, launchRatio: Number(event.target.value) });
                    setDirty(true);
                  }}
                />
                <small>
                  {zh
                    ? "强攻会更快扩张，也会留下更少驻军。"
                    : "Higher pressure expands faster but leaves less reserve."}
                </small>
              </label>
              <label>
                <span>{zh ? "最低出击兵力" : "Minimum launch"}</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={parameters.minimumShips ?? 4}
                  onChange={(event) => {
                    setParameters({ ...parameters, minimumShips: Number(event.target.value) });
                    setDirty(true);
                  }}
                />
              </label>
              <label>
                <span>{zh ? "目标优先级" : "Target priority"}</span>
                <select
                  value={parameters.targetPreference ?? "nearest"}
                  onChange={(event) => {
                    setParameters({
                      ...parameters,
                      targetPreference: event.target.value as "nearest" | "weakest",
                    });
                    setDirty(true);
                  }}
                >
                  <option value="nearest">{zh ? "最近目标" : "Nearest target"}</option>
                  <option value="weakest">{zh ? "最弱目标" : "Weakest target"}</option>
                </select>
              </label>
            </div>
          ) : (
            <label className="strategy-code">
              <span>main.py · Python 3.11 stdlib</span>
              <textarea
                aria-label={zh ? "策略代码" : "Strategy source code"}
                spellCheck={false}
                value={source}
                onChange={(event) => {
                  setSource(event.target.value);
                  setDirty(true);
                }}
              />
            </label>
          )}

          <div className="strategy-editor__actions">
            <button
              className="button button--primary"
              disabled={busy !== null || !dirty}
              onClick={() => void saveDraft()}
              type="button"
            >
              {busy === "save"
                ? zh
                  ? "保存中…"
                  : "Saving…"
                : zh
                  ? "保存私有草稿"
                  : "Save private draft"}
            </button>
            <button
              className="button"
              disabled={busy !== null}
              onClick={() => void simulate()}
              type="button"
            >
              {busy === "simulate"
                ? zh
                  ? "验证中…"
                  : "Validating…"
                : zh
                  ? "运行模拟"
                  : "Run simulation"}
            </button>
            <button
              className="button"
              disabled={busy !== null}
              onClick={() => void resetTemplate()}
              type="button"
            >
              {zh ? "重置平台模板" : "Reset platform template"}
            </button>
          </div>
        </div>

        <aside className="strategy-ai">
          <div className="strategy-ai__meter">
            <span>DEEPSEEK V4 FLASH</span>
            <strong>{workspace.aiCredits.remaining}</strong>
            <small>
              / {workspace.aiCredits.granted} {zh ? "免费额度" : "FREE CREDITS"}
            </small>
          </div>
          <h2>{zh ? "AI 策略副驾" : "AI STRATEGY COPILOT"}</h2>
          <p>
            {zh
              ? "只发送当前草稿和你的目标。AI 结果默认不会写入、更不会发布。"
              : "Only the draft and your goal are sent. AI output is never applied or published automatically."}
          </p>
          <select
            value={assistKind}
            onChange={(event) => setAssistKind(event.target.value as AssistKind)}
          >
            <option value="explain">{zh ? "解释当前策略" : "Explain strategy"}</option>
            <option value="suggest">{zh ? "提出下一步" : "Suggest next step"}</option>
            <option value="patch">{zh ? "生成代码补丁" : "Generate patch"}</option>
          </select>
          <textarea
            placeholder={
              zh ? "例如：减少开局过度扩张" : "For example: reduce over-expansion in the opening"
            }
            rows={3}
            value={assistGoal}
            onChange={(event) => setAssistGoal(event.target.value)}
          />
          <label className="strategy-ai__check">
            <input
              checked={deep}
              onChange={(event) => setDeep(event.target.checked)}
              type="checkbox"
            />
            {zh ? "深度分析（2 次额度）" : "Deep analysis (2 credits)"}
          </label>
          <label className="strategy-ai__check">
            <input
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
              type="checkbox"
            />
            {zh ? "我同意将当前草稿发送给 DeepSeek" : "I agree to send this draft to DeepSeek"}
          </label>
          <button
            className="button button--primary"
            disabled={busy !== null || !consent || dirty}
            onClick={() => void askAi()}
            type="button"
          >
            {busy === "ai"
              ? zh
                ? "分析中…"
                : "Analyzing…"
              : dirty
                ? zh
                  ? "请先保存草稿"
                  : "Save draft first"
                : zh
                  ? "请求 AI 分析"
                  : "Ask AI"}
          </button>
          {assist && (
            <div className="strategy-ai__result">
              <strong>{assist.summary}</strong>
              <p>{assist.reasoning}</p>
              {assist.diff && <pre>{assist.diff}</pre>}
              {assist.diff && (
                <button className="button" onClick={acceptPatch} type="button">
                  {zh ? "接受到草稿（不发布）" : "Apply to draft (not publish)"}
                </button>
              )}
            </div>
          )}
        </aside>
      </section>

      <section className="strategy-lab__lower">
        <article className="panel strategy-validation">
          <p className="eyebrow">VALIDATION / CANDIDATE</p>
          <h2>{zh ? "先证明，再发布。" : "PROVE IT BEFORE PUBLISHING."}</h2>
          <p>
            {workspace.draft.validatedContentHash
              ? zh
                ? `当前草稿已通过固定验证 · ${workspace.draft.validatedContentHash.slice(0, 12)}`
                : `Current draft passed fixed validation · ${workspace.draft.validatedContentHash.slice(0, 12)}`
              : zh
                ? "运行模拟不会改变当前版本、积分或公开战绩。"
                : "Simulation does not change the current version, rating, or public record."}
          </p>
          {simulation && (
            <p className="notice">
              {zh ? "私人策略模拟" : "PRIVATE STRATEGY SIMULATION"} {simulation.publicId} ·{" "}
              {simulation.status.toUpperCase()}
            </p>
          )}
          {simulationRefreshError && (
            <div className="history-error" role="alert">
              <span>{simulationRefreshError}</span>
              <button
                className="button button--small"
                onClick={() => setSimulationRefreshKey((value) => value + 1)}
                type="button"
              >
                ↻ {zh ? "立即重试" : "Retry now"}
              </button>
            </div>
          )}
          {!workspace.publishEligibility.eligible && (
            <p className="strategy-validation__reason">{publishBlockReason()}</p>
          )}
          <button
            className="button button--primary"
            disabled={busy !== null || dirty || !workspace.publishEligibility.eligible}
            onClick={() => void publish()}
            type="button"
          >
            {busy === "publish"
              ? zh
                ? "发布中…"
                : "Publishing…"
              : zh
                ? "发布并设为当前 →"
                : "Publish and set current →"}
          </button>
        </article>

        <article className="panel strategy-versions">
          <p className="eyebrow">IMMUTABLE VERSIONS</p>
          <h2>{zh ? "版本航迹" : "VERSION TRAJECTORY"}</h2>
          <div className="status-list">
            {workspace.versions.map((version) => (
              <div className="status-row" key={version.publicId}>
                <div>
                  <strong>{version.notes || version.publicId}</strong>
                  <p>
                    {formatDate(locale, version.createdAt)} · {version.status.toUpperCase()} ·{" "}
                    {version.source}
                  </p>
                </div>
                {workspace.fleet.currentStrategyVersionId === version.publicId ? (
                  <span className="mode-tag" data-tone="agent">
                    CURRENT
                  </span>
                ) : (
                  <button
                    className="button button--small"
                    disabled={busy !== null || version.status !== "ready"}
                    onClick={() => void selectVersion(version.publicId)}
                    type="button"
                  >
                    {zh ? "恢复" : "Restore"}
                  </button>
                )}
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
