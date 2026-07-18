"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "../../src/api";
import { localPath, messages, type Locale } from "../../src/i18n";

type PlayerState = "loading" | "signed-out" | "needs-fleet" | "ready";

export function SessionAction({ locale }: { locale: Locale }) {
  const zh = locale === "zh";
  const [state, setState] = useState<PlayerState>("loading");

  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<{ authenticated: boolean }>("/api/v1/session")
      .then(async (session) => {
        if (!session.authenticated) {
          setState("signed-out");
          return;
        }
        try {
          await apiFetch("/api/v1/me/fleet", { signal: controller.signal });
          setState("ready");
        } catch (reason) {
          if (reason instanceof Error && reason.name === "AbortError") return;
          setState(
            reason instanceof ApiError && reason.code === "fleet.not_found"
              ? "needs-fleet"
              : "ready",
          );
        }
      })
      .catch(() => setState("signed-out"));
    return () => controller.abort();
  }, []);

  if (state === "loading") return <span className="session-status">•••</span>;
  if (state === "signed-out") {
    const destination = localPath(locale, "/start");
    return (
      <Link
        className="button button--primary button--small"
        href={`/auth/login?returnTo=${encodeURIComponent(destination)}`}
      >
        {zh ? "开始游戏" : "Start playing"}
      </Link>
    );
  }

  return (
    <>
      {state === "ready" && (
        <Link className="session-link" href={localPath(locale, "/command")}>
          {zh ? "我的舰队" : "My fleet"}
        </Link>
      )}
      <Link
        className="button button--primary button--small"
        href={localPath(locale, state === "ready" ? "/arena" : "/start")}
      >
        {state === "ready" ? (zh ? "立即开战" : "Play now") : messages[locale].nav.create}
      </Link>
      <Link
        className="session-link session-link--muted"
        href={`/auth/logout?returnTo=${encodeURIComponent(localPath(locale))}`}
      >
        {messages[locale].nav.logout}
      </Link>
    </>
  );
}
