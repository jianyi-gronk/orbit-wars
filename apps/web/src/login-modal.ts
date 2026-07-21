import { localPath, type Locale } from "./i18n";

export const OPEN_LOGIN_EVENT = "orbit:open-login";

export type OpenLoginDetail = {
  returnTo?: string;
};

export function safeLoginReturnTo(value: string | null | undefined, locale: Locale): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : localPath(locale);
}

export function withLoginPrompt(value: string | null | undefined, locale: Locale): string {
  const destination = new URL(safeLoginReturnTo(value, locale), "https://orbit.invalid");
  destination.searchParams.set("auth", "login");
  return `${destination.pathname}${destination.search}${destination.hash}`;
}

export function requestLogin(returnTo: string): void {
  window.dispatchEvent(
    new CustomEvent<OpenLoginDetail>(OPEN_LOGIN_EVENT, {
      detail: { returnTo },
    }),
  );
}
