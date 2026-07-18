"use client";

import type { Application } from "pixi.js";
import { useEffect, useRef } from "react";
import type { PlanetView } from "../../src/battle";

type BattleStageProps = {
  planets: PlanetView[];
  player: 0 | 1;
  selectedPlanetId: number | null;
  angle: number;
  lowPerformance: boolean;
  onSelect: (planetId: number) => void;
  onAim: (angle: number) => void;
};

type PixiRuntime = typeof import("pixi.js");
type StageState = Pick<BattleStageProps, "planets" | "player" | "selectedPlanetId" | "angle">;

function drawStage(
  app: Application,
  runtime: PixiRuntime,
  host: HTMLDivElement,
  state: StageState,
  select: (planetId: number) => void,
) {
  const { Graphics, Text } = runtime;
  for (const child of app.stage.removeChildren()) child.destroy();
  const width = host.clientWidth;
  const height = host.clientHeight;
  const scaleX = width / 100;
  const scaleY = height / 100;
  const grid = new Graphics();
  for (let ring = 1; ring <= 4; ring += 1) {
    grid.circle(width / 2, height / 2, ring * Math.min(width, height) * 0.11);
  }
  grid.stroke({ color: 0x50616c, alpha: 0.16, width: 1 });
  app.stage.addChild(grid);

  for (const planet of state.planets) {
    const x = planet.x * scaleX;
    const y = planet.y * scaleY;
    const body = new Graphics();
    const color = planet.owner === 0 ? 0x67d8ff : planet.owner === 1 ? 0xff6b57 : 0x89949a;
    body.circle(x, y, Math.max(8, planet.radius * Math.min(scaleX, scaleY)));
    body.fill({ color, alpha: planet.owner === state.player ? 0.86 : 0.5 });
    body.stroke({
      color: state.selectedPlanetId === planet.id ? 0xffd76a : color,
      alpha: 0.9,
      width: state.selectedPlanetId === planet.id ? 3 : 1,
    });
    body.eventMode = "static";
    body.cursor = planet.owner === state.player ? "crosshair" : "default";
    body.on("pointertap", () => select(planet.id));
    app.stage.addChild(body);
    const label = new Text({
      text: `${planet.id} · ${Math.floor(planet.ships)}`,
      style: { fill: 0xf2f5f3, fontFamily: "monospace", fontSize: 11 },
    });
    label.position.set(x + 12, y - 7);
    app.stage.addChild(label);
  }
  const selected = state.planets.find((planet) => planet.id === state.selectedPlanetId);
  if (selected) {
    const trajectory = new Graphics();
    const startX = selected.x * scaleX;
    const startY = selected.y * scaleY;
    trajectory.moveTo(startX, startY);
    trajectory.lineTo(startX + Math.cos(state.angle) * 130, startY + Math.sin(state.angle) * 130);
    trajectory.stroke({ color: 0xffd76a, alpha: 0.72, width: 2 });
    app.stage.addChild(trajectory);
  }
}

export function BattleStage(props: BattleStageProps) {
  const { planets, player, selectedPlanetId, angle, lowPerformance, onSelect, onAim } = props;
  const host = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const runtimeRef = useRef<PixiRuntime | null>(null);
  const stateRef = useRef<StageState>({ planets, player, selectedPlanetId, angle });
  const onSelectRef = useRef(onSelect);

  useEffect(() => {
    stateRef.current = { planets, player, selectedPlanetId, angle };
    onSelectRef.current = onSelect;
  }, [angle, onSelect, planets, player, selectedPlanetId]);

  useEffect(() => {
    let disposed = false;
    let app: Application | null = null;
    void import("pixi.js").then(async (runtime) => {
      if (!host.current || disposed) return;
      app = new runtime.Application();
      await app.init({
        resizeTo: host.current,
        antialias: !lowPerformance,
        backgroundAlpha: 0,
        resolution: lowPerformance ? 1 : Math.min(window.devicePixelRatio, 2),
        autoDensity: true,
      });
      if (disposed || !host.current) {
        app.destroy(true);
        return;
      }
      app.ticker.maxFPS = lowPerformance ? 30 : 60;
      host.current.appendChild(app.canvas);
      appRef.current = app;
      runtimeRef.current = runtime;
      drawStage(app, runtime, host.current, stateRef.current, (id) => onSelectRef.current(id));
    });
    return () => {
      disposed = true;
      appRef.current = null;
      runtimeRef.current = null;
      app?.destroy(true, { children: true });
    };
  }, [lowPerformance]);

  useEffect(() => {
    if (appRef.current && runtimeRef.current && host.current) {
      drawStage(appRef.current, runtimeRef.current, host.current, stateRef.current, (id) =>
        onSelectRef.current(id),
      );
    }
  }, [angle, planets, player, selectedPlanetId]);

  function aimFromPointer(event: React.PointerEvent<HTMLDivElement>) {
    if (selectedPlanetId === null) return;
    const selected = planets.find((planet) => planet.id === selectedPlanetId);
    if (!selected) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const sourceX = bounds.left + (selected.x / 100) * bounds.width;
    const sourceY = bounds.top + (selected.y / 100) * bounds.height;
    onAim(Math.atan2(event.clientY - sourceY, event.clientX - sourceX));
  }

  return (
    <div
      className="battle-stage"
      ref={host}
      onPointerMove={aimFromPointer}
      role="img"
      aria-label="权威战场视图；选择星球后移动指针可预览航线"
    />
  );
}
