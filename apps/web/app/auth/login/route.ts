import { NextRequest, NextResponse } from "next/server";

import {
  RETURN_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  oidcConfig,
  pkceChallenge,
  randomUrlSafe,
  safeReturnTo,
} from "../../../src/auth";

export async function GET(request: NextRequest) {
  const config = oidcConfig(request.nextUrl.origin);
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));
  if (!config) {
    return NextResponse.redirect(new URL(`${returnTo}?auth=unavailable`, request.url));
  }
  const state = randomUrlSafe();
  const verifier = randomUrlSafe(48);
  const authorize = new URL(config.authorizationEndpoint);
  authorize.searchParams.set("client_id", config.clientId);
  authorize.searchParams.set("redirect_uri", config.redirectUri);
  authorize.searchParams.set("response_type", "code");
  authorize.searchParams.set("scope", config.scope);
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("code_challenge", pkceChallenge(verifier));
  authorize.searchParams.set("code_challenge_method", "S256");
  const response = NextResponse.redirect(authorize);
  const options = {
    httpOnly: true,
    maxAge: 600,
    path: "/",
    sameSite: "lax" as const,
    secure: request.nextUrl.protocol === "https:",
  };
  response.cookies.set(STATE_COOKIE, state, options);
  response.cookies.set(VERIFIER_COOKIE, verifier, options);
  response.cookies.set(RETURN_COOKIE, returnTo, options);
  return response;
}
