"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  availableShips,
  initialDraft,
  queueLaunch,
  removeQueuedLaunch,
  selectPlanet,
  setAngle,
  setShipRatio,
  setShips,
  updateQueuedLaunch,
  type CommandDraft,
  type FleetView,
  type PlanetView,
} from "../../src/battle";
import { localPath, type Locale } from "../../src/i18n";
import { BattleStage } from "./BattleStage";
import { TurnCountdown } from "./TurnCountdown";

type Observation = {
  matchId: string;
  step: number;
  player: 0 | 1;
  deadlineAt: string;
  planets: PlanetView[];
  fleets: FleetView[];
};

type LiveMessage = {
  type: string;
  payload?: Observation;
  step?: number;
  deadlineAt?: string;
  code?: string;
  recoverable?: boolean;
  result?: { winnerSlot: number | null; reason: string };
};

export function LiveBattle({ locale, matchId }: { locale: Locale; matchId: string }) {
  const zh = locale === "zh";
  const socket = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const lastSeenStep = useRef(0);
  const submittedSteps = useRef(new Set<number>());
  const finished = useRef(false);
  const draftRef = useRef<CommandDraft>(initialDraft);
  const [observation, setObservation] = useState<Observation | null>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [status, setStatus] = useState(
    zh ? "正在连接权威服务器…" : "Connecting to the authoritative server…",
  );
  const [lowPerformance, setLowPerformance] = useState(false);
  const [connectionEpoch, setConnectionEpoch] = useState(0);
  const [submittedStep, setSubmittedStep] = useState<number | null>(null);
  const planets = useMemo(() => observation?.planets ?? [], [observation?.planets]);
  const fleets = useMemo(() => observation?.fleets ?? [], [observation?.fleets]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    const ticket = sessionStorage.getItem(`orbit.match-ticket.${matchId}`);
    if (!ticket) {
      const timer = window.setTimeout(
        () =>
          setStatus(
            zh
              ? "比赛票据缺失或已过期，请返回竞技场重新创建。"
              : "The match ticket is missing or expired. Return to the arena.",
          ),
        0,
      );
      return () => window.clearTimeout(timer);
    }
    const validTicket = ticket;
    const base =
      process.env.NEXT_PUBLIC_ORBIT_WS_BASE ??
      `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/orbit-api`;
    let disposed = false;
    let attempts = 0;

    function connect() {
      if (disposed || finished.current) return;
      const connection = new WebSocket(
        `${base}/api/live/v1/matches/${encodeURIComponent(matchId)}?ticket=${encodeURIComponent(validTicket)}`,
      );
      socket.current = connection;
      connection.onopen = () => {
        attempts = 0;
        setConnectionEpoch((value) => value + 1);
        setStatus(
          zh ? "已连接，正在同步权威战场。" : "Connected. Syncing the authoritative battlefield.",
        );
        connection.send(
          JSON.stringify({ type: "match.resync", lastSeenStep: lastSeenStep.current }),
        );
      };
      connection.onmessage = (event) => {
        let message: LiveMessage;
        try {
          message = JSON.parse(String(event.data)) as LiveMessage;
        } catch {
          setStatus(zh ? "收到无法解析的服务器消息。" : "Received an unreadable server message.");
          return;
        }
        if (message.type === "match.snapshot" && message.payload?.planets) {
          if (message.payload.step < lastSeenStep.current) return;
          lastSeenStep.current = message.payload.step;
          setObservation(message.payload);
          setDraft(initialDraft);
          setStatus(
            zh
              ? `STEP ${message.payload.step} · 等待指令`
              : `STEP ${message.payload.step} · awaiting command`,
          );
        }
        if (message.type === "match.frame" && message.payload?.planets) {
          if (message.payload.step < lastSeenStep.current) return;
          lastSeenStep.current = message.payload.step;
          setObservation((current) =>
            current
              ? {
                  ...current,
                  planets: message.payload!.planets,
                  fleets: message.payload!.fleets ?? [],
                  step: message.payload!.step,
                  deadlineAt: "",
                }
              : null,
          );
          setDraft(initialDraft);
          setStatus(
            zh
              ? `STEP ${message.payload.step} · 等待指令`
              : `STEP ${message.payload.step} · awaiting command`,
          );
        }
        if (
          message.type === "turn.open" &&
          typeof message.step === "number" &&
          message.deadlineAt
        ) {
          if (message.step < lastSeenStep.current) return;
          lastSeenStep.current = message.step;
          setObservation((current) =>
            current ? { ...current, deadlineAt: message.deadlineAt!, step: message.step! } : null,
          );
        }
        if (message.type === "turn.accepted")
          setStatus(
            zh
              ? `STEP ${message.step} · 服务器已接受`
              : `STEP ${message.step} · accepted by server`,
          );
        if (message.type === "match.error") {
          setStatus(`${zh ? "服务器拒绝" : "Server rejected"}: ${message.code}`);
          if (message.recoverable === false) finished.current = true;
        }
        if (message.type === "match.finished") {
          finished.current = true;
          setStatus(
            `${zh ? "比赛结束" : "Match finished"}: ${message.result?.reason ?? "finished"}`,
          );
        }
      };
      connection.onclose = (event) => {
        if (socket.current === connection) socket.current = null;
        if (disposed || finished.current) return;
        if (event.code === 4401) {
          finished.current = true;
          setStatus(
            zh
              ? "比赛票据已失效，请返回竞技场重新开始。"
              : "The match ticket is invalid. Return to the arena and start again.",
          );
          return;
        }
        const delay = Math.min(4000, 500 * 2 ** attempts);
        attempts += 1;
        setStatus(
          zh
            ? `连接中断，${Math.round(delay / 100) / 10} 秒后重新同步…`
            : `Connection lost. Resyncing in ${Math.round(delay / 100) / 10}s…`,
        );
        reconnectTimer.current = window.setTimeout(connect, delay);
      };
    }

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer.current !== null) window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
      const connection = socket.current;
      socket.current = null;
      connection?.close(1000, "page_unloaded");
    };
  }, [matchId, zh]);

  const sendTurn = useCallback(
    (step: number, commands: CommandDraft["pending"], automatic = false) => {
      const connection = socket.current;
      if (connection?.readyState !== WebSocket.OPEN || submittedSteps.current.has(step)) {
        return false;
      }
      connection.send(
        JSON.stringify({
          type: "turn.submit",
          payload: {
            schemaVersion: 1,
            matchId,
            expectedStep: step,
            commands,
            idempotencyKey: `human-turn-${matchId}-${step}`,
          },
        }),
      );
      submittedSteps.current.add(step);
      setSubmittedStep(step);
      setStatus(
        automatic
          ? zh
            ? `STEP ${step} · 已自动空过`
            : `STEP ${step} · auto-passed`
          : zh
            ? `STEP ${step} · 正在提交`
            : `STEP ${step} · submitting`,
      );
      return true;
    },
    [matchId, zh],
  );

  useEffect(() => {
    if (!observation?.deadlineAt || submittedSteps.current.has(observation.step)) return;
    const delay = Math.max(0, new Date(observation.deadlineAt).getTime() - Date.now() - 120);
    const timer = window.setTimeout(() => void sendTurn(observation.step, [], true), delay);
    return () => window.clearTimeout(timer);
  }, [connectionEpoch, observation?.deadlineAt, observation?.step, sendTurn]);

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") setDraft((value) => setAngle(value, value.angle - 0.08));
      if (event.key === "ArrowRight") setDraft((value) => setAngle(value, value.angle + 0.08));
      if (event.key === "+" || event.key === "=") {
        setDraft((value) => setShips(value, planets, value.ships + 1));
      }
      if (event.key === "-") setDraft((value) => setShips(value, planets, value.ships - 1));
      if (event.key === "Enter") setDraft((value) => queueLaunch(value, planets));
      if (event.key === "Backspace") setDraft((value) => ({ ...value, pending: [] }));
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [planets]);

  const owned = planets.filter((planet) => planet.owner === observation?.player);
  const selected = owned.find((planet) => planet.id === draft.selectedPlanetId);
  const selectedAvailable = selected ? availableShips(draft, planets, selected.id) : 0;
  const originName = (planetId: number) => {
    const index = owned.findIndex((planet) => planet.id === planetId);
    return `${zh ? "己方星球" : "OWNED PLANET"} ${String(Math.max(0, index) + 1).padStart(2, "0")}`;
  };
  function submit() {
    if (!observation) return;
    sendTurn(observation.step, draftRef.current.pending);
  }

  return (
    <main className="tactical-shell">
      <header className="tactical-topbar">
        <Link href={localPath(locale, "/arena")} className="tactical-brand">
          ORBIT / WARS
        </Link>
        <div className="match-ident">
          <span>LIVE MATCH</span>
          <strong>{matchId}</strong>
        </div>
        <TurnCountdown deadlineAt={observation?.deadlineAt ?? ""} />
      </header>
      <section className="battle-grid">
        <div className="stage-wrap">
          <BattleStage
            planets={planets}
            fleets={fleets}
            player={observation?.player ?? 0}
            selectedPlanetId={draft.selectedPlanetId}
            angle={draft.angle}
            lowPerformance={lowPerformance}
            onSelect={(id) =>
              setDraft((value) => selectPlanet(value, planets, observation?.player ?? 0, id))
            }
            onAim={(angle) => setDraft((value) => setAngle(value, angle))}
          />
          <div className="stage-status" aria-live="polite">
            {status}
          </div>
        </div>
        <aside className="command-rail" aria-label={zh ? "战术指令面板" : "Tactical command panel"}>
          <p className="eyebrow">COMMAND VECTOR / {observation?.step ?? "—"}</p>
          <h1>{zh ? "选择。瞄准。发射。" : "Select. Aim. Launch."}</h1>
          <p className="rail-note">
            {zh
              ? "客户端只预览；库存、碰撞和胜负由服务器裁定。"
              : "The client previews; the server decides inventory, collisions, and results."}
          </p>
          <fieldset>
            <legend>01 / {zh ? "源星" : "ORIGIN"}</legend>
            <div className="planet-buttons">
              {owned.map((planet) => (
                <button
                  className={draft.selectedPlanetId === planet.id ? "is-selected" : ""}
                  key={planet.id}
                  onClick={() =>
                    setDraft((value) =>
                      selectPlanet(value, planets, observation?.player ?? 0, planet.id),
                    )
                  }
                >
                  {originName(planet.id)}
                  <small>
                    {Math.floor(planet.ships)} {zh ? "兵力" : "ships"}
                  </small>
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>02 / {zh ? "航向与兵力" : "VECTOR & FORCE"}</legend>
            <label>
              {zh ? "角度" : "Angle"} <output>{((draft.angle * 180) / Math.PI).toFixed(1)}°</output>
              <input
                type="range"
                min="0"
                max={(Math.PI * 2).toString()}
                step="0.01"
                value={draft.angle}
                onChange={(event) =>
                  setDraft((value) => setAngle(value, Number(event.target.value)))
                }
              />
            </label>
            <label>
              {zh ? "舰船" : "Ships"} <output>{draft.ships}</output>
              <input
                type="range"
                min="1"
                max={Math.max(1, selectedAvailable)}
                value={draft.ships}
                onChange={(event) =>
                  setDraft((value) => setShips(value, planets, Number(event.target.value)))
                }
              />
            </label>
            <div className="force-presets" aria-label={zh ? "兵力快捷档" : "Force presets"}>
              {[0.25, 0.5, 0.75, 1].map((ratio) => (
                <button
                  disabled={!selected || selectedAvailable < 1}
                  key={ratio}
                  onClick={() => setDraft((value) => setShipRatio(value, planets, ratio))}
                  type="button"
                >
                  {ratio === 1 ? "ALL" : `${ratio * 100}%`}
                </button>
              ))}
            </div>
            <button
              className="queue-button"
              disabled={!selected || selectedAvailable < 1}
              onClick={() => setDraft((value) => queueLaunch(value, planets))}
              type="button"
            >
              {zh ? "加入待提交" : "Queue launch"}
            </button>
          </fieldset>
          <section className="pending-list" aria-label={zh ? "待提交命令" : "Pending commands"}>
            {draft.pending.length ? (
              <ol>
                {draft.pending.map((command, index) => (
                  <li key={`${command.fromPlanetId}-${index}`}>
                    <div>
                      <strong>{originName(command.fromPlanetId)}</strong>
                      <span>{((command.angle * 180) / Math.PI).toFixed(0)}°</span>
                    </div>
                    <label>
                      <span>{zh ? "兵力" : "FORCE"}</span>
                      <input
                        min="1"
                        onChange={(event) =>
                          setDraft((value) =>
                            updateQueuedLaunch(value, planets, index, Number(event.target.value)),
                          )
                        }
                        type="number"
                        value={command.ships}
                      />
                    </label>
                    <button
                      aria-label={zh ? `删除第 ${index + 1} 条命令` : `Remove command ${index + 1}`}
                      onClick={() => setDraft((value) => removeQueuedLaunch(value, index))}
                      type="button"
                    >
                      {zh ? "删除" : "REMOVE"}
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <p>
                {zh
                  ? "没有指令；截止前会自动提交空动作。"
                  : "No commands; an empty action will be auto-submitted before the deadline."}
              </p>
            )}
          </section>
          {draft.error && (
            <p className="command-error" role="alert">
              {draft.error}
            </p>
          )}
          <button
            className="commit-button"
            disabled={!observation || submittedStep === observation.step}
            onClick={submit}
            type="button"
          >
            {zh ? "确认本回合指令" : "Commit turn"}
          </button>
          <label className="performance-toggle">
            <input
              checked={lowPerformance}
              onChange={(event) => setLowPerformance(event.target.checked)}
              type="checkbox"
            />{" "}
            {zh ? "低性能模式" : "Low-performance mode"}
          </label>
          <p className="keyboard-help">
            {zh
              ? "键盘：← → 航向　+ − 兵力　Enter 加入　Backspace 清空"
              : "Keyboard: ← → heading  + − ships  Enter queue  Backspace clear"}
          </p>
        </aside>
      </section>
    </main>
  );
}
