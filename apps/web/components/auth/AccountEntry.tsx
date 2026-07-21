"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch, type AuthSession } from "../../src/api";
import { localPath, messages, type Locale } from "../../src/i18n";

export function AccountEntry({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<AuthSession>("/api/auth/session", { signal: controller.signal })
      .then(setSession)
      .catch(() => setSession({ authenticated: false }));
    return () => controller.abort();
  }, [pathname]);

  if (session === null) return <span className="account-entry account-entry--loading">•••</span>;
  if (!session.authenticated) {
    const href = `${localPath(locale, "/auth")}?returnTo=${encodeURIComponent(pathname)}`;
    return (
      <Link className="account-entry account-entry--signin" href={href}>
        {messages[locale].nav.login}
      </Link>
    );
  }

  async function logout() {
    try {
      await apiFetch<void>("/api/auth/logout", { method: "POST" });
    } finally {
      setSession({ authenticated: false });
      router.push(localPath(locale));
      router.refresh();
    }
  }

  return (
    <details className="account-menu">
      <summary>
        <span aria-hidden="true">◉</span>
        {session.displayName || session.email || (locale === "zh" ? "指挥官" : "Commander")}
      </summary>
      <div>
        <small>{session.email || session.subject}</small>
        <Link href={localPath(locale, "/command")}>
          {locale === "zh" ? "指挥中心" : "Command center"}
        </Link>
        <Link href={localPath(locale, "/strategy-lab")}>
          {locale === "zh" ? "策略实验室" : "Strategy lab"}
        </Link>
        <span className="account-menu__pending">
          {locale === "zh" ? "账户设置 · 即将开放" : "Account settings · Coming soon"}
        </span>
        <button onClick={() => void logout()} type="button">
          {messages[locale].nav.logout}
        </button>
      </div>
    </details>
  );
}
