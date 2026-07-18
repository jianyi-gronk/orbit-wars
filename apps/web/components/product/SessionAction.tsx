"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, apiFetch, type Fleet, type FleetProfile } from "../../src/api";
import { type Locale } from "../../src/i18n";
import { resolveMissionAction, type MissionAction } from "../../src/mission";

export function SessionAction({ locale }: { locale: Locale }) {
  const [action, setAction] = useState<MissionAction | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<{ authenticated: boolean }>("/api/v1/session", {
      signal: controller.signal,
    })
      .then(async (session) => {
        if (!session.authenticated) {
          setAction(resolveMissionAction(locale, { authenticated: false }));
          return;
        }
        try {
          const fleet = await apiFetch<Fleet>("/api/v1/me/fleet", {
            signal: controller.signal,
          });
          const profile = await apiFetch<FleetProfile>(
            `/api/public/v1/fleet-profiles/${fleet.publicId}`,
            { signal: controller.signal },
          );
          const currentVersion = profile.versions.find(
            (version) => version.publicId === fleet.currentStrategyVersionId,
          );
          setAction(
            resolveMissionAction(locale, {
              authenticated: true,
              hasFleet: true,
              currentStrategyStatus: currentVersion?.status ?? null,
            }),
          );
        } catch (reason) {
          if (reason instanceof Error && reason.name === "AbortError") return;
          setAction(
            resolveMissionAction(
              locale,
              reason instanceof ApiError && reason.code === "fleet.not_found"
                ? { authenticated: true, hasFleet: false }
                : { authenticated: true, incomplete: true },
            ),
          );
        }
      })
      .catch((reason) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setAction(resolveMissionAction(locale, { authenticated: false }));
      });
    return () => controller.abort();
  }, [locale]);

  if (!action) return <span className="session-status">•••</span>;

  return (
    <Link
      className="button button--primary button--small mission-action"
      data-mission-state={action.state}
      href={action.href}
    >
      {action.label}
    </Link>
  );
}
