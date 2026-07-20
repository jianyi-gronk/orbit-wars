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

  it("keeps Human command training-only, recoverable, and hidden behind its feature flag", () => {
    const arena = readFileSync("app/arena/ArenaForm.tsx", "utf8");
    const battle = readFileSync("components/battle/LiveBattle.tsx", "utf8");
    const stage = readFileSync("components/battle/BattleStage.tsx", "utf8");

    expect(arena).toContain("humanPlayEnabled && control ===");
    expect(arena).toContain('setMode("training")');
    expect(arena).toContain("Human Beta 仅开放训练赛");
    expect(arena).toContain("Human Beta is training-only");
    expect(arena).toContain('localStorage.setItem("orbit.human-tutorial.v1"');
    expect(battle).toContain('type: "match.resync"');
    expect(battle).toContain("submittedSteps.current.has(step)");
    expect(battle).toContain("sendTurn(observation.step, [], true)");
    expect(battle).toContain("500 * 2 ** attempts");
    expect(battle).not.toContain("P-{planet.id}");
    expect(stage).toContain("showPlanetIds = false");
  });

  it("keeps the home mission flow keyboard-ready and motion-safe", () => {
    const home = readFileSync("components/product/HomeExperience.tsx", "utf8");
    const layout = readFileSync("app/layout.tsx", "utf8");
    const css = readFileSync("app/game-ux.css", "utf8");

    expect(home).toContain('["ArrowDown", "PageDown", "ArrowUp", "PageUp", "Home", "End"]');
    expect(home).toContain('matchMedia("(prefers-reduced-motion: reduce)")');
    expect(home).toContain('window.addEventListener("wheel", onWheel');
    expect(home).not.toContain('container.addEventListener("wheel", onWheel');
    expect(home).toContain('aria-label={zh ? "首页场景" : "Home scenes"}');
    expect(layout).toContain("<GlobalInteractionFX />");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("scroll-snap-type: y mandatory");
  });

  it("keeps the homepage battle feed real, lightweight, and motion-safe", () => {
    const feed = readFileSync("components/product/HomeBattleFeed.tsx", "utf8");
    const home = readFileSync("components/product/HomeExperience.tsx", "utf8");
    const css = readFileSync("app/game-ux.css", "utf8");

    expect(home).toContain('variant="preview"');
    expect(home).toContain('variant="latest"');
    expect(feed).toContain("/api/public/v1/matches?period=all&limit=3");
    expect(feed).toContain("/segments/0");
    expect(feed).not.toContain("/segments/20");
    expect(feed).toContain("reconstructSegment(records).slice(0, 20)");
    expect(feed).toContain("reducedMotion");
    expect(feed).toContain("!document.hidden");
    expect(css).toContain(".home-battle-preview__link:hover");
    expect(css).toContain(".home-match-card:hover strong");
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
    expect(player).toContain("messages[locale].replay.loading");
    expect(player).not.toContain("messages[locale].common.loading");
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

  it("keeps the replay-to-Agent handoff explicit and key-free", () => {
    const player = readFileSync("components/battle/ReplayPlayer.tsx", "utf8");
    const handoff = readFileSync("src/public-replay.ts", "utf8");
    const css = readFileSync("app/replay.css", "utf8");

    expect(player).toContain('copyPublicReplay("analysis")');
    expect(player).toContain('copyPublicReplay("replay")');
    expect(player).toContain('copyPublicReplay("data")');
    expect(player).toContain('aria-live="polite"');
    expect(handoff).toContain("keyEvents: compact.events.slice(0, 20)");
    expect(handoff).not.toContain("AgentKey");
    expect(handoff).not.toContain("owk_");
    expect(css).toMatch(
      /\.replay-handoff__actions \.replay-handoff__primary:hover:not\(:disabled\)[\s\S]*?color: #080b0d/,
    );
  });

  it("keeps the in-platform strategy path private, bilingual, and explicitly consented", () => {
    const lab = readFileSync("app/strategy-lab/StrategyLab.tsx", "utf8");
    const mission = readFileSync("src/mission.ts", "utf8");
    const start = readFileSync("app/start/StartFlow.tsx", "utf8");

    expect(mission).toContain('"needs-strategy": { path: "/strategy-lab"');
    expect(mission).not.toContain('"needs-agent":');
    expect(start).toContain("不需要 Agent Key");
    expect(start).toContain("no Agent Key required");
    expect(lab).toContain("草稿默认私有");
    expect(lab).toContain("Drafts stay private");
    expect(lab).toContain("我同意将当前草稿发送给 DeepSeek");
    expect(lab).toContain("I agree to send this draft to DeepSeek");
    expect(lab).toContain("Apply to draft (not publish)");
    expect(lab).not.toContain("localStorage");
    expect(lab).not.toContain("sessionStorage");
  });

  it("keeps the trusted match-to-replay loop recoverable and server-gated", () => {
    const arena = readFileSync("app/arena/ArenaForm.tsx", "utf8");
    const status = readFileSync("app/match/MatchStatusView.tsx", "utf8");
    const lab = readFileSync("app/strategy-lab/StrategyLab.tsx", "utf8");
    const header = readFileSync("components/product/SiteHeader.tsx", "utf8");

    expect(arena).toContain("`/match/${created.publicId}`");
    expect(status).toContain("activeStatuses");
    expect(status).toContain("apiFetchWithRetry");
    expect(status).toContain("match.replayPublicId");
    expect(status).toContain("Retry now");
    expect(lab).toContain("workspace.publishEligibility.eligible");
    expect(lab).toContain('searchParams.get("fromReplay")');
    expect(lab).toContain("Back to replay");
    expect(header).toContain('href={localPath(locale, "/arena")}');
    expect(header).toContain('href={localPath(locale, "/leaderboard")}');
    expect(header).toContain('href={localPath(locale, "/command")}');
    expect(header).not.toContain("mission-menu");
    expect(header).not.toContain("<SessionAction");
  });

  it("keeps the central sun visually aligned with the simple Kaggle reference", () => {
    const stage = readFileSync("components/battle/BattleStage.tsx", "utf8");
    const css = readFileSync("app/replay.css", "utf8");

    expect(stage).toContain("new runtime.FillGradient");
    expect(stage).toContain("sunRadius * 3");
    expect(stage).toContain("sunBody.circle(sunX, sunY, sunRadius)");
    expect(stage).toContain("sunBody.fill(assets.sunBody)");
    expect(stage).not.toContain("hazardRing");
    expect(stage).not.toContain("solarFlares");
    expect(stage).not.toContain("coronaPoints");
    expect(css).toMatch(/\.replay-grid-overlay::after[\s\S]*?transparent 40% 60%/);
  });

  it("keeps leaderboard and history semantics audience-first and bilingual", () => {
    const competition = readFileSync("components/product/PublicCompetition.tsx", "utf8");
    const route = readFileSync("app/[locale]/[[...slug]]/page.tsx", "utf8");
    const replay = readFileSync("components/battle/ReplayPlayer.tsx", "utf8");
    const css = readFileSync("app/product.css", "utf8");

    expect(route).toContain('["score", "win_rate", "wins"]');
    expect(competition).toContain("Beta(1,1)");
    expect(competition).toContain("BATTLE HEAT");
    expect(competition).toContain("战况强度");
    expect(competition).toContain("match.highlights.map");
    expect(competition).toContain('<details className="history-details">');
    expect(replay).toContain('searchParams.get("step")');
    expect(css).toContain('.history-intensity[data-band="volatile"]');
  });

  it("keeps the Command next mission dynamic and the one-time key out of storage", () => {
    const command = readFileSync("app/command/CommandCenter.tsx", "utf8");
    const handoff = readFileSync("src/agent-handoff.ts", "utf8");
    const clipboard = readFileSync("src/clipboard.ts", "utf8");

    for (const state of [
      "copy-handoff",
      "needs-agent-key",
      "needs-ready-strategy",
      "battle-ready",
    ]) {
      expect(command).toContain(state);
    }
    expect(command).toContain('aria-live="polite"');
    expect(command).not.toContain("navigator.clipboard");
    expect(handoff).not.toContain("localStorage");
    expect(handoff).not.toContain("sessionStorage");
    expect(clipboard).toContain("clipboard timeout");
    expect(clipboard).toContain('document.execCommand("copy")');
  });

  it("keeps multiline display titles clear of glyph collisions", () => {
    const home = readFileSync("components/product/HomeExperience.tsx", "utf8");
    const gameCss = readFileSync("app/game-ux.css", "utf8");
    const productCss = readFileSync("app/product.css", "utf8");
    const replayCss = readFileSync("app/replay.css", "utf8");

    expect(gameCss).toMatch(/\.scene-copy h1\s*\{[\s\S]*?\/0\.98 var\(--ow-font-display\)/);
    expect(gameCss).toMatch(/\.network-copy h2,[\s\S]*?\/0\.98 var\(--ow-font-display\)/);
    expect(gameCss).toMatch(
      /@media \(width <= 48rem\)[\s\S]*?\.scene-copy h1[\s\S]*?line-height: 1/,
    );
    expect(productCss).toMatch(/\.section-heading h2\s*\{[\s\S]*?\/1 var\(--ow-font-display\)/);
    expect(productCss).toMatch(/\.display-title\s*\{[\s\S]*?\/1 var\(--ow-font-display\)/);
    expect(replayCss).toMatch(
      /\.replay-error-panel h1\s*\{[\s\S]*?\/1\.08 var\(--ow-font-display\)/,
    );
    expect(home).toContain("<span>不需要先有 Agent。</span>");
    expect(home).toContain("<span>NO AGENT REQUIRED.</span>");
  });
});
