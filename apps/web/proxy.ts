import { NextRequest, NextResponse } from "next/server";

import { isLocale, type Locale } from "./src/i18n";

const PUBLIC_FILE = /\.[^/]+$/;

function preferredLocale(request: NextRequest): Locale {
  const stored = request.cookies.get("orbit_locale")?.value;
  if (stored && isLocale(stored)) return stored;
  return request.headers.get("accept-language")?.toLowerCase().startsWith("en") ? "en" : "zh";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/orbit-api") ||
    pathname.startsWith("/auth") ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }
  const first = pathname.split("/")[1] ?? "";
  if (!isLocale(first)) {
    const url = request.nextUrl.clone();
    url.pathname = `/${preferredLocale(request)}${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(url);
  }
  const headers = new Headers(request.headers);
  headers.set("x-orbit-locale", first);
  return NextResponse.next({ request: { headers } });
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
