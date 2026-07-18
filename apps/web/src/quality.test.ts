import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { frameBudgetReport, replaySeekReadBound } from "./performance";

describe("release performance and accessibility budgets", () => {
  it("enforces 60 FPS standard and 30 FPS low-performance frame budgets", () => {
    expect(frameBudgetReport(Array(120).fill(15.8), false).withinBudget).toBe(true);
    expect(frameBudgetReport(Array(120).fill(31.5), true).withinBudget).toBe(true);
    expect(frameBudgetReport(Array(120).fill(18), false).withinBudget).toBe(false);
  });

  it("bounds replay seek work to one checkpoint segment", () => {
    expect(replaySeekReadBound(39)).toBe(20);
    expect(replaySeekReadBound(40)).toBe(1);
    expect(replaySeekReadBound(499)).toBeLessThanOrEqual(20);
  });

  it("keeps keyboard labels and reduced-motion fallbacks in the tactical surface", () => {
    const page = readFileSync("components/battle/LiveBattle.tsx", "utf8");
    const css = readFileSync("app/battle/demo/tactical.css", "utf8");
    expect(page).toContain("键盘：");
    expect(page).toContain("Keyboard:");
    expect(page).toContain('aria-live="polite"');
    expect(page).toContain('"战术指令面板"');
    expect(page).toContain('"Tactical command panel"');
    expect(css).toContain("prefers-reduced-motion: reduce");
  });

  it("keeps the home mission flow keyboard-ready and motion-safe", () => {
    const home = readFileSync("components/product/HomeExperience.tsx", "utf8");
    const layout = readFileSync("app/layout.tsx", "utf8");
    const css = readFileSync("app/game-ux.css", "utf8");

    expect(home).toContain('["ArrowDown", "PageDown", "ArrowUp", "PageUp", "Home", "End"]');
    expect(home).toContain('matchMedia("(prefers-reduced-motion: reduce)")');
    expect(home).toContain('aria-label={zh ? "首页场景" : "Home scenes"}');
    expect(layout).toContain("<GlobalInteractionFX />");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("scroll-snap-type: y mandatory");
  });

  it("keeps the orbital world optional, motion-safe, and disposable", () => {
    const home = readFileSync("components/product/HomeExperience.tsx", "utf8");
    const world = readFileSync("components/product/OrbitalWorld.tsx", "utf8");
    const css = readFileSync("app/game-ux.css", "utf8");

    expect(home).toContain("<OrbitalWorld");
    expect(world).toContain('await import("three")');
    expect(world).toContain('aria-hidden="true"');
    expect(world).toContain('document.addEventListener("visibilitychange"');
    expect(world).toContain("reducedMotionRef.current");
    expect(world).toContain("window.cancelAnimationFrame(animationFrame)");
    expect(world).toContain("entry.dispose()");
    expect(world).toContain("renderer.forceContextLoss()");
    expect(css).toMatch(/\.orbital-world\s*\{[\s\S]*?pointer-events: none/);
  });

  it("loads the localized replay surface and collapses dense events into accessible markers", () => {
    const layout = readFileSync("app/layout.tsx", "utf8");
    const player = readFileSync("components/battle/ReplayPlayer.tsx", "utf8");
    const css = readFileSync("app/replay.css", "utf8");

    expect(layout).toContain('import "./replay.css"');
    expect(player).toContain("aria-label={label}");
    expect(player).toContain("data-edge={eventEdge(position)}");
    expect(css).toContain(".replay-stage-wrap .battle-stage");
    expect(css).toMatch(/\.replay-stage-wrap\s*\{[\s\S]*?aspect-ratio: 1/);
    expect(css).toMatch(/\.replay-event-track button span[\s\S]*opacity: 0/);
    expect(css).toContain(".replay-event-track button:hover span");
    expect(css).toMatch(
      /\.replay-controls \.replay-play-button:hover:not\(:disabled\)[\s\S]*?color: #080b0d/,
    );
    expect(css).toContain("@media (max-width: 620px)");
  });

  it("keeps the central sun visually aligned with the simple Kaggle reference", () => {
    const stage = readFileSync("components/battle/BattleStage.tsx", "utf8");

    expect(stage).toContain("new runtime.FillGradient");
    expect(stage).toContain("sunRadius * 2.8");
    expect(stage).toContain("sunBody.circle(sunX, sunY, sunRadius)");
    expect(stage).not.toContain("hazardRing");
    expect(stage).not.toContain("solarFlares");
    expect(stage).not.toContain("coronaPoints");
  });
});
