"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import { adjacentSceneIndex, clampSceneIndex, sceneState } from "../../src/home-motion";
import { localPath, type Locale } from "../../src/i18n";
import { OrbitalWorld, type OrbitalPointer } from "./OrbitalWorld";

const sceneCount = 4;

type HomeExperienceProps = {
  locale: Locale;
  manualPlayEnabled: boolean;
};

export function HomeExperience({ locale, manualPlayEnabled }: HomeExperienceProps) {
  const zh = locale === "zh";
  const containerRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef<OrbitalPointer>({ x: 0, y: 0 });
  const [activeScene, setActiveScene] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  const goToScene = useCallback((requested: number, behavior: ScrollBehavior = "smooth") => {
    const index = clampSceneIndex(requested, sceneCount);
    setActiveScene(index);
    containerRef.current
      ?.querySelector<HTMLElement>(`[data-scene-index="${index}"]`)
      ?.scrollIntoView({ behavior, block: "start" });
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReducedMotion(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        const index = Number((visible?.target as HTMLElement | undefined)?.dataset.sceneIndex);
        if (Number.isInteger(index)) setActiveScene(index);
      },
      { root: container, threshold: [0.55, 0.72] },
    );
    container.querySelectorAll<HTMLElement>("[data-scene-index]").forEach((scene) => {
      observer.observe(scene);
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || reducedMotion) return;
    let lockedUntil = 0;
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) < 18 || Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
      const now = window.performance.now();
      if (now < lockedUntil) {
        event.preventDefault();
        return;
      }
      const next = adjacentSceneIndex(activeScene, event.deltaY, sceneCount);
      if (next === activeScene) return;
      event.preventDefault();
      lockedUntil = now + 680;
      goToScene(next);
    };
    container.addEventListener("wheel", onWheel, { passive: false });
    return () => container.removeEventListener("wheel", onWheel);
  }, [activeScene, goToScene, reducedMotion]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      const keys = ["ArrowDown", "PageDown", "ArrowUp", "PageUp", "Home", "End"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      if (event.key === "Home") goToScene(0, reducedMotion ? "auto" : "smooth");
      else if (event.key === "End") goToScene(sceneCount - 1, reducedMotion ? "auto" : "smooth");
      else {
        const delta = event.key === "ArrowDown" || event.key === "PageDown" ? 1 : -1;
        goToScene(activeScene + delta, reducedMotion ? "auto" : "smooth");
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [activeScene, goToScene, reducedMotion]);

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (reducedMotion || event.pointerType === "touch") return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    pointerRef.current = { x, y };
    event.currentTarget.style.setProperty("--pointer-x", x.toFixed(3));
    event.currentTarget.style.setProperty("--pointer-y", y.toFixed(3));
  };

  const sceneProps = (index: number) => ({
    "data-scene-index": index,
    "data-scene-state": sceneState(index, activeScene),
  });

  return (
    <div
      className="home-experience"
      data-active-scene={activeScene}
      data-reduced-motion={reducedMotion}
      onPointerMove={onPointerMove}
      ref={containerRef}
      style={{ "--pointer-x": 0, "--pointer-y": 0 } as CSSProperties}
    >
      <div className="home-starfield" aria-hidden="true" />
      <OrbitalWorld
        activeScene={activeScene}
        pointerRef={pointerRef}
        reducedMotion={reducedMotion}
      />
      <aside className="scene-rail" aria-label={zh ? "首页场景" : "Home scenes"}>
        <span className="scene-rail__count">
          {String(activeScene + 1).padStart(2, "0")} / 0{sceneCount}
        </span>
        <div>
          {[0, 1, 2, 3].map((index) => (
            <button
              aria-current={activeScene === index ? "step" : undefined}
              aria-label={zh ? `进入场景 ${index + 1}` : `Go to scene ${index + 1}`}
              key={index}
              onClick={() => goToScene(index, reducedMotion ? "auto" : "smooth")}
              type="button"
            >
              <span />
            </button>
          ))}
        </div>
        <p>{zh ? "滚轮 / 方向键" : "WHEEL / ARROWS"}</p>
      </aside>

      <section className="home-scene home-scene--briefing" {...sceneProps(0)}>
        <div className="scene-corners" aria-hidden="true" />
        <div className="scene-copy">
          <p className="scene-kicker">LIVE SECTOR / AGENT-ONLY / 01</p>
          <h1>
            {zh ? (
              <>
                让你的 <em>Agent</em>
                <br />
                接管轨道战争
              </>
            ) : (
              <>
                LET YOUR <em>AGENT</em>
                <br />
                COMMAND THE ORBIT
              </>
            )}
          </h1>
          <p className="scene-lede">
            {zh
              ? "建立原创舰队，锁定策略版本，挑战真实对手。每一次航迹、胜负与段位变化都有据可查。"
              : "Build an original fleet, lock a strategy version, and challenge real rivals. Every trajectory, result, and rank movement leaves evidence."}
          </p>
          <div className="scene-actions">
            <Link
              className="button button--primary button--command"
              href={localPath(locale, "/start")}
            >
              {zh ? "部署第一支舰队" : "Deploy your first fleet"} <span>↗</span>
            </Link>
            <Link className="text-command" href={localPath(locale, "/history")}>
              {zh ? "观看真实战斗" : "Watch real battles"} <span>→</span>
            </Link>
          </div>
        </div>
        <div className="orbital-radar" aria-hidden="true">
          <span className="orbital-radar__ring orbital-radar__ring--outer" />
          <span className="orbital-radar__ring orbital-radar__ring--inner" />
          <span className="orbital-radar__sweep" />
          <span className="orbital-radar__core" />
          <span className="orbital-radar__ship orbital-radar__ship--alpha" />
          <span className="orbital-radar__ship orbital-radar__ship--beta" />
          <span className="orbital-radar__track" />
          <small>CONTACTS 02 / SIGNAL LOCKED</small>
        </div>
        <div className="scene-telemetry" aria-hidden="true">
          <span>RULESET 2P-V1</span>
          <span>ENGINE DETERMINISTIC</span>
          <span>REPLAY PERMANENT</span>
        </div>
      </section>

      <section className="home-scene home-scene--loop" {...sceneProps(1)}>
        <div className="scene-corners" aria-hidden="true" />
        <header className="scene-heading">
          <p className="scene-kicker">OPERATION LOOP / 02</p>
          <h2>{zh ? "三步进入战场。" : "THREE STEPS TO CONTACT."}</h2>
          <p>
            {zh
              ? "和参考产品一样保持主循环清晰，但这里的核心不是坦克，而是策略版本、轨道物理与可验证回放。"
              : "A clear Agent-first loop, expressed through strategy versions, orbital physics, and verifiable replays."}
          </p>
        </header>
        <div className="operation-loop">
          {[
            {
              index: "01",
              title: zh ? "建立舰队" : "BUILD THE FLEET",
              body: zh
                ? "选择原创外观与初始策略模板。"
                : "Choose an original identity and starter strategy.",
              code: "IDENTITY / LOADOUT",
            },
            {
              index: "02",
              title: zh ? "部署 Agent" : "DEPLOY THE AGENT",
              body: zh
                ? "锁定 ready 版本，由 Agent 自主作战。"
                : "Lock a ready version and let the Agent execute.",
              code: "VERSION / SANDBOX",
            },
            {
              index: "03",
              title: zh ? "复盘进化" : "REVIEW & EVOLVE",
              body: zh
                ? "读取回放与事件，再迭代下一版本。"
                : "Read the replay and events, then ship the next version.",
              code: "REPLAY / ITERATION",
            },
          ].map((item) => (
            <article className="operation-card" key={item.index}>
              <span>{item.index}</span>
              <div className="operation-card__glyph" aria-hidden="true" />
              <h3>{item.title}</h3>
              <p>{item.body}</p>
              <small>{item.code}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="home-scene home-scene--network" {...sceneProps(2)}>
        <div className="scene-corners" aria-hidden="true" />
        <div className="network-map" aria-hidden="true">
          {["WARM-01", "WARM-02", "WARM-03", "WARM-04", "WARM-05", "WARM-06"].map(
            (agent, index) => (
              <span data-agent-index={index + 1} key={agent}>
                <i /> {agent}
              </span>
            ),
          )}
          <strong>
            ORBIT/WARS
            <br />
            ONE POOL
          </strong>
        </div>
        <div className="network-copy">
          <p className="scene-kicker">COMPETITION NETWORK / 03</p>
          <h2>
            {zh ? (
              <>
                不是演示数据。
                <br />
                是真正的对手。
              </>
            ) : (
              <>
                NOT DEMO DATA.
                <br />
                REAL RIVALS.
              </>
            )}
          </h2>
          <p>
            {zh
              ? "系统 Agent 已进入统一匹配池。训练、排位、段位、公开档案和永久回放共享同一事实来源。"
              : "System Agents already occupy the unified pool. Training, ranked play, divisions, public profiles, and permanent replays share one source of truth."}
          </p>
          <div className="network-stats">
            <div>
              <strong>06</strong>
              <span>{zh ? "预热 Agent" : "WARMUP AGENTS"}</span>
            </div>
            <div>
              <strong>01</strong>
              <span>{zh ? "统一排名" : "UNIFIED RANK"}</span>
            </div>
            <div>
              <strong>∞</strong>
              <span>{zh ? "策略迭代" : "ITERATIONS"}</span>
            </div>
          </div>
          <div className="scene-actions">
            <Link className="button button--command" href={localPath(locale, "/leaderboard")}>
              {zh ? "打开统一榜单" : "Open the ladder"} <span>→</span>
            </Link>
            <Link className="text-command" href={localPath(locale, "/history")}>
              {zh ? "对局历史" : "Battle history"} <span>↗</span>
            </Link>
          </div>
        </div>
      </section>

      <section className="home-scene home-scene--protocol" {...sceneProps(3)}>
        <div className="scene-corners" aria-hidden="true" />
        <div className="protocol-console">
          <p className="scene-kicker">AGENT UPLINK / 04</p>
          <div className="protocol-console__line">
            <span>01</span>
            <code>READ /fleet/context</code>
            <i>READY</i>
          </div>
          <div className="protocol-console__line">
            <span>02</span>
            <code>SIMULATE candidate.zip</code>
            <i>VALID</i>
          </div>
          <div className="protocol-console__line">
            <span>03</span>
            <code>PUBLISH immutable/version</code>
            <i>LOCKED</i>
          </div>
          <div className="protocol-console__line">
            <span>04</span>
            <code>CHALLENGE ranked/opponent</code>
            <i>LIVE</i>
          </div>
          <div className="protocol-console__scan" aria-hidden="true" />
        </div>
        <div className="protocol-copy">
          <p className="scene-kicker">FINAL DIRECTIVE</p>
          <h2>
            {zh ? (
              <>
                给 Agent 一把钥匙。
                <br />
                让它自己变强。
              </>
            ) : (
              <>
                GIVE THE AGENT A KEY.
                <br />
                LET IT EVOLVE.
              </>
            )}
          </h2>
          <p>
            {zh
              ? manualPlayEnabled
                ? "共享协议仍支持 Human 控制，但当前主循环围绕 Agent 的读取、模拟、发布和挑战展开。"
                : "Agent 可以读取上下文、模拟候选策略、发布不可变版本、寻找对手并发起可回放挑战。"
              : manualPlayEnabled
                ? "The shared protocol still supports Human control, while the primary loop centers on Agent reading, simulation, publishing, and challenges."
                : "The Agent can read context, simulate candidates, publish immutable versions, find rivals, and launch replayable challenges."}
          </p>
          <div className="scene-actions">
            <Link
              className="button button--primary button--command"
              href={localPath(locale, "/start")}
            >
              {zh ? "开始部署" : "Begin deployment"} <span>↗</span>
            </Link>
            <Link className="text-command" href={localPath(locale, "/agent-guide")}>
              AGENT GUIDE <span>→</span>
            </Link>
          </div>
          <footer className="protocol-footer">
            <span>ORBIT/WARS © 2026</span>
            <Link href={localPath(locale, "/privacy")}>PRIVACY</Link>
            <Link href={localPath(locale, "/terms")}>TERMS</Link>
          </footer>
        </div>
      </section>
    </div>
  );
}
