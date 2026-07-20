"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LocaleSwitcher } from "./LocaleSwitcher";
import { localPath, messages, type Locale } from "../../src/i18n";

export function SiteHeader({ locale = "zh" }: { locale?: Locale }) {
  const t = messages[locale].nav;
  const pathname = usePathname();
  const active = (path: string) => pathname === localPath(locale, path);
  return (
    <header className="product-header">
      <Link className="product-wordmark" href={localPath(locale)} aria-label="Orbit Wars">
        <span aria-hidden="true">◎</span>
        <strong>ORBIT/WARS</strong>
        <small>SECTOR ONLINE</small>
      </Link>
      <nav aria-label={locale === "zh" ? "主导航" : "Primary navigation"}>
        <Link
          aria-current={active("/arena") ? "page" : undefined}
          href={localPath(locale, "/arena")}
        >
          <span>01</span>
          {t.arena}
        </Link>
        <Link
          aria-current={active("/leaderboard") ? "page" : undefined}
          href={localPath(locale, "/leaderboard")}
        >
          <span>02</span>
          {t.leaderboard}
        </Link>
        <Link
          aria-current={active("/command") ? "page" : undefined}
          href={localPath(locale, "/command")}
        >
          <span>03</span>
          {t.command}
        </Link>
      </nav>
      <div className="header-actions">
        <LocaleSwitcher locale={locale} />
      </div>
    </header>
  );
}
