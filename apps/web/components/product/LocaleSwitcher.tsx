"use client";

import { usePathname, useSearchParams } from "next/navigation";

import { swapLocale, type Locale } from "../../src/i18n";

export function LocaleSwitcher({ locale }: { locale: Locale }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const target: Locale = locale === "zh" ? "en" : "zh";

  function switchLanguage() {
    document.cookie = `orbit_locale=${target}; Path=/; Max-Age=31536000; SameSite=Lax`;
    const query = searchParams.toString();
    window.location.assign(`${swapLocale(pathname, target)}${query ? `?${query}` : ""}`);
  }

  return (
    <button className="language-switch" onClick={switchLanguage} type="button">
      {target === "zh" ? "中文" : "EN"}
    </button>
  );
}
