"use client";

import { useEffect, useState } from "react";

export function TurnCountdown({ deadlineAt }: { deadlineAt: string }) {
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    const update = () => {
      const deadline = Date.parse(deadlineAt);
      setRemaining(Number.isFinite(deadline) ? Math.max(0, deadline - Date.now()) : 0);
    };
    update();
    const timer = window.setInterval(update, 50);
    return () => window.clearInterval(timer);
  }, [deadlineAt]);
  return (
    <output className="turn-countdown" aria-live="polite" aria-label="本回合剩余时间">
      {(remaining / 1000).toFixed(1)}s
    </output>
  );
}
