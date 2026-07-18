"use client";

import { useEffect, useRef, useState } from "react";

type Pulse = {
  id: number;
  x: number;
  y: number;
};

export function GlobalInteractionFX() {
  const [pulses, setPulses] = useState<Pulse[]>([]);
  const nextId = useRef(0);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const timers = new Set<number>();
    const onPointerDown = (event: PointerEvent) => {
      if (media.matches || event.button !== 0) return;
      const origin =
        event.target instanceof Element
          ? event.target.closest("a, button, summary, [role='button']")
          : null;
      if (!(origin instanceof HTMLElement) || origin.matches(":disabled, [aria-disabled='true']"))
        return;

      const id = nextId.current++;
      setPulses((current) => [...current.slice(-5), { id, x: event.clientX, y: event.clientY }]);
      origin.dataset.pressed = "true";
      const timer = window.setTimeout(() => {
        setPulses((current) => current.filter((pulse) => pulse.id !== id));
        delete origin.dataset.pressed;
        timers.delete(timer);
      }, 620);
      timers.add(timer);
    };
    document.addEventListener("pointerdown", onPointerDown, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  return (
    <div className="interaction-fx" aria-hidden="true">
      {pulses.map((pulse) => (
        <span className="interaction-pulse" key={pulse.id} style={{ left: pulse.x, top: pulse.y }}>
          <i />
          <b />
        </span>
      ))}
    </div>
  );
}
