"use client";

import type { Application } from "pixi.js";
import { useEffect, useRef } from "react";
import {
  fleetDirection,
  formatPlanetLabel,
  type FleetView,
  type PlanetView,
} from "../../src/battle";

const EMPTY_FLEETS: FleetView[] = [];

type BattleStageProps = {
  planets: PlanetView[];
  fleets?: FleetView[];
  player: 0 | 1;
  selectedPlanetId: number | null;
  angle: number;
  lowPerformance: boolean;
  showPlanetIds?: boolean;
  onSelect: (planetId: number) => void;
  onAim: (angle: number) => void;
};

type PixiRuntime = typeof import("pixi.js");
type StageState = Pick<BattleStageProps, "planets" | "player" | "selectedPlanetId" | "angle"> & {
  fleets: FleetView[];
  showPlanetIds: boolean;
};

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
    const radius = Math.max(8, planet.radius * Math.min(scaleX, scaleY));
    const body = new Graphics();
    const color = planet.owner === 0 ? 0x67d8ff : planet.owner === 1 ? 0xff6b57 : 0x89949a;
    body.circle(x, y, radius);
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
      text: formatPlanetLabel(planet.id, planet.ships, state.showPlanetIds),
      style: {
        fill: 0xf2f5f3,
        fontFamily: "monospace",
        fontSize: Math.max(9, Math.min(12, radius * 0.72)),
        fontWeight: "600",
      },
    });
    if (state.showPlanetIds) {
      label.position.set(x + radius + 4, y - label.height / 2);
    } else {
      label.anchor.set(0.5);
      label.position.set(x, y);
    }
    app.stage.addChild(label);
  }

  for (const fleet of state.fleets) {
    const x = fleet.x * scaleX;
    const y = fleet.y * scaleY;
    const direction = fleetDirection(fleet.angle);
    const perpendicular = { x: -direction.y, y: direction.x };
    const color = fleet.owner === 0 ? 0x67d8ff : 0xff6b57;

    const trail = new Graphics();
    trail
      .moveTo(x - direction.x * 28, y - direction.y * 28)
      .lineTo(x - direction.x * 5, y - direction.y * 5)
      .stroke({ color, alpha: 0.18, width: 2 });
    trail
      .moveTo(x - direction.x * 16, y - direction.y * 16)
      .lineTo(x - direction.x * 4, y - direction.y * 4)
      .stroke({ color, alpha: 0.62, width: 2 });
    app.stage.addChild(trail);

    const vessel = new Graphics();
    vessel
      .moveTo(x + direction.x * 8, y + direction.y * 8)
      .lineTo(
        x - direction.x * 5 + perpendicular.x * 4.5,
        y - direction.y * 5 + perpendicular.y * 4.5,
      )
      .lineTo(
        x - direction.x * 3 - perpendicular.x * 4.5,
        y - direction.y * 3 - perpendicular.y * 4.5,
      )
      .closePath()
      .fill({ color, alpha: 0.95 })
      .stroke({ color: 0xf2f5f3, alpha: 0.78, width: 1 });
    app.stage.addChild(vessel);

    const strength = new Text({
      text: String(Math.floor(fleet.ships)),
      style: {
        fill: color,
        fontFamily: "monospace",
        fontSize: 10,
        fontWeight: "700",
        stroke: { color: 0x071015, width: 3 },
      },
    });
    strength.anchor.set(0.5);
    strength.position.set(x + perpendicular.x * 11, y + perpendicular.y * 11);
    app.stage.addChild(strength);
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
  const {
    planets,
    fleets = EMPTY_FLEETS,
    player,
    selectedPlanetId,
    angle,
    lowPerformance,
    showPlanetIds = true,
    onSelect,
    onAim,
  } = props;
  const host = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const runtimeRef = useRef<PixiRuntime | null>(null);
  const stateRef = useRef<StageState>({
    planets,
    fleets,
    player,
    selectedPlanetId,
    angle,
    showPlanetIds,
  });
  const onSelectRef = useRef(onSelect);

  useEffect(() => {
    stateRef.current = { planets, fleets, player, selectedPlanetId, angle, showPlanetIds };
    onSelectRef.current = onSelect;
  }, [angle, fleets, onSelect, planets, player, selectedPlanetId, showPlanetIds]);

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
  }, [angle, fleets, planets, player, selectedPlanetId, showPlanetIds]);

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
