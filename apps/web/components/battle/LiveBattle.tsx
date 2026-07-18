"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  initialDraft,
  queueLaunch,
  selectPlanet,
  setAngle,
  setShips,
  type FleetView,
  type PlanetView,
} from "../../src/battle";
import { idempotencyKey } from "../../src/api";
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

export function LiveBattle({ locale, matchId }: { locale: Locale; matchId: string }) {
  const zh = locale === "zh";
  const socket = useRef<WebSocket | null>(null);
  const [observation, setObservation] = useState<Observation | null>(null);
  const [draft, setDraft] = useState(initialDraft);
  const [status, setStatus] = useState(
    zh ? "正在连接权威服务器…" : "Connecting to the authoritative server…",
  );
  const [lowPerformance, setLowPerformance] = useState(false);
  const planets = useMemo(() => observation?.planets ?? [], [observation?.planets]);
  const fleets = useMemo(() => observation?.fleets ?? [], [observation?.fleets]);

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
    const base =
      process.env.NEXT_PUBLIC_ORBIT_WS_BASE ??
      `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/orbit-api`;
    const connection = new WebSocket(
      `${base}/api/live/v1/matches/${encodeURIComponent(matchId)}?ticket=${encodeURIComponent(ticket)}`,
    );
    socket.current = connection;
    connection.onopen = () =>
      setStatus(zh ? "已连接，等待战场快照。" : "Connected. Waiting for the battlefield snapshot.");
    connection.onmessage = (event) => {
      const message = JSON.parse(String(event.data)) as {
        type: string;
        payload?: Observation;
        step?: number;
        deadlineAt?: string;
        code?: string;
        result?: { winnerSlot: number | null; reason: string };
      };
      if (message.type === "match.snapshot" && message.payload?.planets) {
        setObservation(message.payload);
        setDraft(initialDraft);
        setStatus(
          zh
            ? `STEP ${message.payload.step} · 等待指令`
            : `STEP ${message.payload.step} · awaiting command`,
        );
      }
      if (message.type === "match.frame" && message.payload?.planets) {
        setObservation((current) =>
          current
            ? {
                ...current,
                planets: message.payload!.planets,
                fleets: message.payload!.fleets ?? [],
                step: message.payload!.step,
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
      if (message.type === "turn.open" && typeof message.step === "number" && message.deadlineAt) {
        setObservation((current) =>
          current ? { ...current, deadlineAt: message.deadlineAt!, step: message.step! } : null,
        );
      }
      if (message.type === "turn.accepted")
        setStatus(
          zh ? `STEP ${message.step} · 服务器已接受` : `STEP ${message.step} · accepted by server`,
        );
      if (message.type === "match.error")
        setStatus(`${zh ? "服务器拒绝" : "Server rejected"}: ${message.code}`);
      if (message.type === "match.finished")
        setStatus(`${zh ? "比赛结束" : "Match finished"}: ${message.result?.reason ?? "finished"}`);
    };
    connection.onclose = (event) =>
      setStatus(`${zh ? "连接关闭" : "Connection closed"} · ${event.reason || event.code}`);
    return () => {
      socket.current = null;
      connection.close();
    };
  }, [matchId, zh]);

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
  function submit() {
    if (!observation || socket.current?.readyState !== WebSocket.OPEN) return;
    socket.current.send(
      JSON.stringify({
        type: "turn.submit",
        payload: {
          schemaVersion: 1,
          matchId,
          expectedStep: observation.step,
          commands: draft.pending,
          idempotencyKey: idempotencyKey("human-turn"),
        },
      }),
    );
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
                  P-{planet.id} <small>{Math.floor(planet.ships)} ships</small>
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
                max={Math.max(1, selected?.ships ?? 1)}
                value={draft.ships}
                onChange={(event) =>
                  setDraft((value) => setShips(value, planets, Number(event.target.value)))
                }
              />
            </label>
            <button
              className="queue-button"
              onClick={() => setDraft((value) => queueLaunch(value, planets))}
            >
              {zh ? "加入待提交" : "Queue launch"}
            </button>
          </fieldset>
          <section className="pending-list" aria-label={zh ? "待提交命令" : "Pending commands"}>
            <p>
              {draft.pending.length
                ? `${draft.pending.length} commands queued`
                : zh
                  ? "没有指令；截止时提交空动作。"
                  : "No commands; an empty action will be submitted."}
            </p>
          </section>
          {draft.error && (
            <p className="command-error" role="alert">
              {draft.error}
            </p>
          )}
          <button className="commit-button" disabled={!observation} onClick={submit}>
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
