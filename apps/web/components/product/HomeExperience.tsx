"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import {
  adjacentSceneIndex,
  clampSceneIndex,
  createWheelGestureState,
  reduceWheelGesture,
  sceneState,
} from "../../src/home-motion";
import { localPath, type Locale } from "../../src/i18n";
import { HomeBattleFeed } from "./HomeBattleFeed";
import { OrbitalWorld, type OrbitalPointer } from "./OrbitalWorld";

const sceneCount = 4;

type HomeExperienceProps = {
  locale: Locale;
};

export function HomeExperience({ locale }: HomeExperienceProps) {
  const zh = locale === "zh";
  const containerRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef<OrbitalPointer>({ x: 0, y: 0 });
  const activeSceneRef = useRef(0);
  const wheelGestureRef = useRef(createWheelGestureState());
  const [activeScene, setActiveScene] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  const goToScene = useCallback((requested: number, behavior: ScrollBehavior = "smooth") => {
    const index = clampSceneIndex(requested, sceneCount);
    activeSceneRef.current = index;
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
          .filter((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.55)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        const index = Number((visible?.target as HTMLElement | undefined)?.dataset.sceneIndex);
        if (Number.isInteger(index)) {
          activeSceneRef.current = index;
          setActiveScene(index);
        }
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
    if (!container) return;
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
      event.preventDefault();
      const result = reduceWheelGesture(
        wheelGestureRef.current,
        event.deltaY,
        window.performance.now(),
      );
      wheelGestureRef.current = result.state;
      if (result.direction === 0) return;
      const current = activeSceneRef.current;
      const next = adjacentSceneIndex(current, result.direction, sceneCount);
      if (next === current) return;
      goToScene(next, reducedMotion ? "auto" : "smooth");
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => window.removeEventListener("wheel", onWheel);
  }, [goToScene, reducedMotion]);

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
          <p className="scene-kicker">LIVE SECTOR / STRATEGY-FIRST / 01</p>
          <h1>
            {zh ? (
              <>
                让你的 <em>策略</em>
                <br />
                接管轨道战争
              </>
            ) : (
              <>
                LET YOUR <em>STRATEGY</em>
                <br />
                COMMAND THE ORBIT
              </>
            )}
          </h1>
          <p className="scene-lede">
            {zh
              ? "建立原创舰队，直接使用平台模板、调参或写代码，再挑战真实对手——不需要先准备 Agent Key。"
              : "Build an original fleet, use a platform template, tune or code it, then challenge real rivals—no Agent Key required."}
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
        <HomeBattleFeed
          active={activeScene === 0}
          locale={locale}
          reducedMotion={reducedMotion}
          variant="preview"
        />
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
              : "A clear strategy-first loop, expressed through immutable versions, orbital physics, and verifiable replays."}
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
              title: zh ? "迭代策略" : "ITERATE STRATEGY",
              body: zh
                ? "站内调参或写代码，用训练模拟证明候选。"
                : "Tune or code in-platform, then prove the candidate in training.",
              code: "DRAFT / SIMULATION",
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
        <HomeBattleFeed
          active={activeScene === 2}
          locale={locale}
          reducedMotion={reducedMotion}
          variant="latest"
        />
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
          <p className="scene-kicker">STRATEGY LAB / 04</p>
          <div className="protocol-console__line">
            <span>01</span>
            <code>EDIT private/draft</code>
            <i>READY</i>
          </div>
          <div className="protocol-console__line">
            <span>02</span>
            <code>SIMULATE candidate</code>
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
                <span>不需要先有 Agent。</span>
                <span>在平台内进化。</span>
              </>
            ) : (
              <>
                <span>NO AGENT REQUIRED.</span>
                <span>EVOLVE IN-PLATFORM.</span>
              </>
            )}
          </h2>
          <p>
            {zh
              ? "从可编辑模板开始，使用站内实验室保存私有草稿、训练模拟和发布不可变版本；AI 副驾是可选项。"
              : "Start from an editable template, save private drafts, run training simulations, and publish immutable versions in Strategy Lab. AI assistance is optional."}
          </p>
          <div className="scene-actions">
            <Link
              className="button button--primary button--command"
              href={localPath(locale, "/strategy-lab")}
            >
              {zh ? "打开策略实验室" : "Open Strategy Lab"} <span>↗</span>
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
