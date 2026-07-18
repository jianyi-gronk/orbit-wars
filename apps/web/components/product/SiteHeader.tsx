"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LocaleSwitcher } from "./LocaleSwitcher";
import { SessionAction } from "./SessionAction";
import { localPath, messages, type Locale } from "../../src/i18n";

export function SiteHeader({ locale = "zh" }: { locale?: Locale }) {
  const t = messages[locale].nav;
  const zh = locale === "zh";
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
        <details className="mission-menu">
          <summary>
            {zh ? "任务菜单" : "MISSION MENU"}
            <span aria-hidden="true">+</span>
          </summary>
          <div className="mission-menu__panel">
            <p>{zh ? "战术档案" : "TACTICAL ARCHIVE"}</p>
            <Link href={localPath(locale, "/history")}>
              <span>01</span>
              {t.history}
            </Link>
            <Link href={localPath(locale, "/agent-guide")}>
              <span>02</span>Agent Guide
            </Link>
            <Link href={localPath(locale, "/about")}>
              <span>03</span>
              {zh ? "规则与世界" : "Rulebook"}
            </Link>
            <Link href={localPath(locale, "/qa")}>
              <span>04</span>Q&amp;A
            </Link>
            <Link href={localPath(locale, "/updates")}>
              <span>05</span>
              {zh ? "更新日志" : "Updates"}
            </Link>
            <Link href={`/auth/logout?returnTo=${encodeURIComponent(localPath(locale))}`}>
              <span>06</span>
              {messages[locale].nav.logout}
            </Link>
          </div>
        </details>
        <SessionAction locale={locale} />
        <LocaleSwitcher locale={locale} />
      </div>
    </header>
  );
}
