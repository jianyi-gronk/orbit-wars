"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch, idempotencyKey, type Fleet } from "../../src/api";
import { humanPlayEnabled } from "../../src/features";
import { errorMessage, localPath, type Locale } from "../../src/i18n";
import { canQueue } from "../../src/product";

type Control = "human" | "agent";
type Mode = "training" | "ranked";
type Offer = {
  opponentFleetId: string;
  opponentName: string;
  reason: string;
  ratingDifference: number;
  recentRepeats: number;
  ratingMultiplier: number;
};
type CreatedMatch = {
  publicId: string;
  ticket: string;
  playerSlot: number;
  mode: Mode;
  status: string;
};

export function ArenaForm({
  locale = "zh",
  initialControl = "agent",
}: {
  locale?: Locale;
  initialControl?: Control;
}) {
  const zh = locale === "zh";
  const enabledInitialControl = humanPlayEnabled ? initialControl : "agent";
  const [control, setControl] = useState<Control>(enabledInitialControl);
  const [mode, setMode] = useState<Mode>("training");
  const [confirmed, setConfirmed] = useState(false);
  const [fleet, setFleet] = useState<Fleet | null>(null);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [created, setCreated] = useState<CreatedMatch | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [tutorialStep, setTutorialStep] = useState(0);
  const [tutorialComplete, setTutorialComplete] = useState(true);

  useEffect(() => {
    if (!humanPlayEnabled) return;
    const complete = localStorage.getItem("orbit.human-tutorial.v1") === "complete";
    const timer = window.setTimeout(() => setTutorialComplete(complete), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const findOffer = useCallback(
    async (nextControl: Control) => {
      setBusy(true);
      setError("");
      setErrorCode("");
      setCreated(null);
      try {
        const owned = fleet ?? (await apiFetch<Fleet>("/api/v1/me/fleet"));
        setFleet(owned);
        setOffer(
          await apiFetch<Offer>(
            `/api/v1/matchmaking/offers?fleet_id=${encodeURIComponent(owned.publicId)}&controller_type=${nextControl}`,
          ),
        );
      } catch (reason) {
        setOffer(null);
        const code = reason instanceof ApiError ? reason.code : undefined;
        setErrorCode(code ?? "unknown");
        setError(errorMessage(locale, code));
      } finally {
        setBusy(false);
      }
    },
    [fleet, locale],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void findOffer(enabledInitialControl), 0);
    return () => window.clearTimeout(timer);
  }, [enabledInitialControl, findOffer]);

  async function queue() {
    if (!fleet || !offer) return;
    setBusy(true);
    setError("");
    setErrorCode("");
    try {
      const match = await apiFetch<CreatedMatch>("/api/v1/matches", {
        body: JSON.stringify({
          controllerType: control,
          fleetId: fleet.publicId,
          idempotencyKey: idempotencyKey("web-match"),
          mode,
          opponentControllerType: "agent",
          opponentFleetId: offer.opponentFleetId,
        }),
        method: "POST",
      });
      sessionStorage.setItem(`orbit.match-ticket.${match.publicId}`, match.ticket);
      setCreated(match);
    } catch (reason) {
      const code = reason instanceof ApiError ? reason.code : undefined;
      setErrorCode(code ?? "unknown");
      setError(errorMessage(locale, code));
    } finally {
      setBusy(false);
    }
  }

  function choose(next: Control) {
    setControl(next);
    if (next === "human") setMode("training");
    setConfirmed(false);
    void findOffer(next);
  }

  function finishTutorial() {
    localStorage.setItem("orbit.human-tutorial.v1", "complete");
    setTutorialComplete(true);
    setTutorialStep(0);
  }

  const tutorial = [
    zh
      ? ["选择源星", "点选己方星球；星球内部数字就是当前可用兵力。"]
      : ["Select an origin", "Choose an owned planet. Its number is the current force."],
    zh
      ? ["拖拽瞄准", "在正方形战场上点击或拖拽，预览舰队航向。"]
      : ["Aim directly", "Click or drag across the square battlefield to preview a heading."],
    zh
      ? ["分配兵力", "使用 25% / 50% / 75% / ALL 快捷档，再加入命令队列。"]
      : ["Allocate force", "Use 25% / 50% / 75% / ALL, then add the launch to the queue."],
    zh
      ? ["按时提交", "每回合约 2.5 秒；来不及操作时平台会自动提交空动作。"]
      : ["Commit on time", "Each turn is about 2.5s. The platform auto-passes if you do nothing."],
  ];

  return (
    <section className="panel arena-panel">
      <p className="eyebrow">01 / MATCH CONTROL</p>
      <h2>
        {humanPlayEnabled
          ? zh
            ? "这场由谁操作？"
            : "Who controls this match?"
          : zh
            ? "确认出战配置"
            : "Confirm deployment"}
      </h2>
      {humanPlayEnabled ? (
        <div className="choice-grid">
          {(["human", "agent"] as const).map((value) => (
            <button
              aria-pressed={control === value}
              className="choice-card"
              key={value}
              onClick={() => choose(value)}
              type="button"
            >
              <span className="mode-tag" data-tone={value}>
                {value.toUpperCase()}
              </span>
              <strong>
                {value === "human"
                  ? zh
                    ? "手动指挥"
                    : "Manual command"
                  : zh
                    ? "策略执行"
                    : "Strategy execution"}
              </strong>
              <small>
                {value === "human"
                  ? zh
                    ? "通过实时票据连接服务器。"
                    : "Connect live with a scoped match ticket."
                  : zh
                    ? "锁定当前 ready 版本。"
                    : "Lock the current ready version."}
              </small>
            </button>
          ))}
        </div>
      ) : (
        <div className="agent-lock" role="status">
          <span aria-hidden="true" className="agent-lock__mark">
            ◎
          </span>
          <div className="agent-lock__copy">
            <strong>{zh ? "Agent 自主执行" : "Agent autonomous"}</strong>
            <small>
              {zh ? "开赛时锁定当前 ready 策略。" : "Locks the ready strategy at match start."}
            </small>
          </div>
          <span className="mode-tag" data-tone="agent">
            READY
          </span>
        </div>
      )}
      {humanPlayEnabled && control === "human" && !tutorialComplete && (
        <section className="human-tutorial" aria-live="polite">
          <p className="eyebrow">
            HUMAN COMMAND / {String(tutorialStep + 1).padStart(2, "0")} OF 04
          </p>
          <h3>{tutorial[tutorialStep][0]}</h3>
          <p>{tutorial[tutorialStep][1]}</p>
          <div className="toolbar">
            <button className="button" onClick={finishTutorial} type="button">
              {zh ? "跳过教学" : "Skip tutorial"}
            </button>
            <button
              className="button button--primary"
              onClick={() =>
                tutorialStep === tutorial.length - 1
                  ? finishTutorial()
                  : setTutorialStep((value) => value + 1)
              }
              type="button"
            >
              {tutorialStep === tutorial.length - 1
                ? zh
                  ? "完成并继续 →"
                  : "Finish and continue →"
                : zh
                  ? "下一步 →"
                  : "Next →"}
            </button>
          </div>
        </section>
      )}
      <div className="field">
        <label htmlFor="mode">02 / {zh ? "选择模式" : "CHOOSE MODE"}</label>
        <select
          id="mode"
          disabled={control === "human"}
          onChange={(event) => {
            setMode(event.target.value as Mode);
            setConfirmed(false);
          }}
          value={mode}
        >
          <option value="training">{zh ? "训练 / 不计分" : "Training / unrated"}</option>
          <option disabled={control === "human"} value="ranked">
            {zh ? "排位 / 改变统一 rating" : "Ranked / changes unified rating"}
          </option>
        </select>
      </div>
      {control === "human" && (
        <p className="notice">
          {zh
            ? "Human Beta 仅开放训练赛，不改变统一 rating。"
            : "Human Beta is training-only and does not change the unified rating."}
        </p>
      )}
      {offer && (
        <div className="opponent-card">
          <div>
            <strong className="opponent-card__title">
              <span>03 / {zh ? "你的对手" : "YOUR RIVAL"}</span>
              <span>{offer.opponentName}</span>
            </strong>
            <p>
              {zh
                ? `分差 ${offer.ratingDifference} · 近期交手 ${offer.recentRepeats}`
                : `Rating gap ${offer.ratingDifference} · ${offer.recentRepeats} recent repeats`}
            </p>
          </div>
          <span className="mode-tag">×{offer.ratingMultiplier.toFixed(2)}</span>
        </div>
      )}
      {mode === "ranked" && (
        <label className="notice">
          <input
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            type="checkbox"
          />{" "}
          {zh
            ? `我确认：本场由 ${control.toUpperCase()} 控制，结果会改变舰队唯一 rating。`
            : `I confirm ${control.toUpperCase()} control and that this result changes the fleet's only rating.`}
        </label>
      )}
      {error && errorCode !== "matchmaking.unavailable" && (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      )}
      {errorCode === "matchmaking.unavailable" && (
        <div className="empty-opponent" role="status">
          <p className="eyebrow">WAITING FOR CONTACT</p>
          <h3>{zh ? "暂时没有可匹配的对手" : "No rival is available yet"}</h3>
          <p>
            {zh
              ? "比赛至少需要两支舰队。你可以稍后重新匹配；本地演示环境会提供训练对手。"
              : "A match needs two fleets. Retry shortly; the local demo environment provides a training rival."}
          </p>
        </div>
      )}
      <div className="toolbar">
        {!created ? (
          <button
            className="button button--primary"
            disabled={
              busy ||
              !offer ||
              !canQueue(mode, confirmed) ||
              (control === "human" && !tutorialComplete)
            }
            onClick={() => void queue()}
            type="button"
          >
            {busy
              ? zh
                ? "正在联络服务器…"
                : "Contacting server…"
              : zh
                ? mode === "training"
                  ? "立即开一把训练赛 →"
                  : "确认排位并开战 →"
                : mode === "training"
                  ? "Start training match →"
                  : "Confirm ranked battle →"}
          </button>
        ) : (
          <>
            <span className="mode-tag" data-tone={mode}>
              {created.status.toUpperCase()} · {created.publicId}
            </span>
            {control === "human" ? (
              <Link
                className="button button--primary"
                href={localPath(locale, `/battle/${created.publicId}`)}
              >
                {zh ? "进入实时战术台" : "Enter live battle"}
              </Link>
            ) : (
              <Link className="button button--primary" href={localPath(locale, "/command")}>
                {zh ? "查看执行状态" : "View execution"}
              </Link>
            )}
          </>
        )}
        {!offer && !busy && (
          <button className="button" onClick={() => void findOffer(control)} type="button">
            {zh ? "重新匹配" : "Retry offer"}
          </button>
        )}
      </div>
    </section>
  );
}
