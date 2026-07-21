"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { apiFetch, type AuthSession } from "../../src/api";
import { localPath, messages, type Locale } from "../../src/i18n";
import {
  OPEN_LOGIN_EVENT,
  safeLoginReturnTo,
  type OpenLoginDetail,
} from "../../src/login-modal";
import { LoginModal } from "./LoginModal";

export function AccountEntry({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginReturnTo, setLoginReturnTo] = useState(pathname);

  const currentReturnTo = useCallback(() => {
    const current = new URL(window.location.href);
    current.searchParams.delete("auth");
    return `${current.pathname}${current.search}${current.hash}`;
  }, []);

  const closeLogin = useCallback(() => {
    setLoginOpen(false);
    const current = new URL(window.location.href);
    if (current.searchParams.get("auth") === "login") {
      current.searchParams.delete("auth");
      window.history.replaceState(
        window.history.state,
        "",
        `${current.pathname}${current.search}${current.hash}`,
      );
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void apiFetch<AuthSession>("/api/auth/session", { signal: controller.signal })
      .then(setSession)
      .catch(() => setSession({ authenticated: false }));
    return () => controller.abort();
  }, [pathname]);

  useEffect(() => {
    function openLogin(returnTo?: string) {
      setLoginReturnTo(safeLoginReturnTo(returnTo ?? currentReturnTo(), locale));
      setLoginOpen(true);
    }

    function onLoginRequest(event: Event) {
      openLogin((event as CustomEvent<OpenLoginDetail>).detail?.returnTo);
    }

    window.addEventListener(OPEN_LOGIN_EVENT, onLoginRequest);
    if (new URLSearchParams(window.location.search).get("auth") === "login") openLogin();
    return () => window.removeEventListener(OPEN_LOGIN_EVENT, onLoginRequest);
  }, [currentReturnTo, locale, pathname]);

  if (session === null) return <span className="account-entry account-entry--loading">•••</span>;
  if (!session.authenticated) {
    return (
      <>
        <button
          className="account-entry account-entry--signin"
          onClick={() => {
            setLoginReturnTo(currentReturnTo());
            setLoginOpen(true);
          }}
          type="button"
        >
          {messages[locale].nav.login}
        </button>
        <LoginModal
          locale={locale}
          onClose={closeLogin}
          open={loginOpen}
          returnTo={loginReturnTo}
        />
      </>
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
