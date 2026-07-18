import { createHash, randomBytes } from "node:crypto";

export const AUTH_COOKIE = "orbit_session";
export const STATE_COOKIE = "orbit_oidc_state";
export const VERIFIER_COOKIE = "orbit_oidc_verifier";
export const RETURN_COOKIE = "orbit_oidc_return";

export function randomUrlSafe(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function safeReturnTo(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/zh/command";
}

export function oidcConfig(origin: string) {
  const issuer = process.env.OIDC_ISSUER?.replace(/\/$/, "");
  const clientId = process.env.OIDC_CLIENT_ID;
  if (!issuer || !clientId) return null;
  return {
    authorizationEndpoint: process.env.OIDC_AUTHORIZATION_ENDPOINT ?? `${issuer}/authorize`,
    clientId,
    clientSecret: process.env.OIDC_CLIENT_SECRET,
    redirectUri: process.env.OIDC_REDIRECT_URI ?? `${origin}/auth/callback`,
    scope: process.env.OIDC_SCOPE ?? "openid profile email",
    tokenEndpoint: process.env.OIDC_TOKEN_ENDPOINT ?? `${issuer}/oauth/token`,
  };
}
