import { NextRequest, NextResponse } from "next/server";

import {
  AUTH_COOKIE,
  RETURN_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  oidcConfig,
  safeReturnTo,
} from "../../../src/auth";

export async function GET(request: NextRequest) {
  const config = oidcConfig(request.nextUrl.origin);
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get(STATE_COOKIE)?.value;
  const verifier = request.cookies.get(VERIFIER_COOKIE)?.value;
  const returnTo = safeReturnTo(request.cookies.get(RETURN_COOKIE)?.value ?? null);
  if (!config || !code || !state || state !== expectedState || !verifier) {
    return NextResponse.redirect(new URL(`${returnTo}?auth=invalid`, request.url));
  }
  const body = new URLSearchParams({
    client_id: config.clientId,
    code,
    code_verifier: verifier,
    grant_type: "authorization_code",
    redirect_uri: config.redirectUri,
  });
  if (config.clientSecret) body.set("client_secret", config.clientSecret);
  const tokenResponse = await fetch(config.tokenEndpoint, {
    body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    method: "POST",
  });
  if (!tokenResponse.ok)
    return NextResponse.redirect(new URL(`${returnTo}?auth=failed`, request.url));
  const tokens = (await tokenResponse.json()) as { access_token?: string; expires_in?: number };
  if (!tokens.access_token)
    return NextResponse.redirect(new URL(`${returnTo}?auth=failed`, request.url));
  const response = NextResponse.redirect(new URL(returnTo, request.url));
  response.cookies.set(AUTH_COOKIE, tokens.access_token, {
    httpOnly: true,
    maxAge: Math.min(tokens.expires_in ?? 3600, 86400),
    path: "/",
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
  });
  for (const cookie of [STATE_COOKIE, VERIFIER_COOKIE, RETURN_COOKIE])
    response.cookies.delete(cookie);
  return response;
}
