# GitHub authentication

Orbit Wars launches with GitHub as the only visible registration and sign-in method. The first
successful GitHub callback creates a `User` and `OAuthIdentity`; later callbacks reuse that
identity and issue a new 30-day opaque `orbit_session`. GitHub access tokens are used only during
the callback and are not persisted.

Email credentials, verification codes, and password reset remain dormant behind
`ORBIT_PASSWORD_AUTH_ENABLED=false`. Do not enable that flag until email delivery and its separate
security runbook are reviewed.

## Required production configuration

Create a GitHub OAuth App with an HTTPS callback URL matching:

```text
https://YOUR_DOMAIN/orbit-api/api/auth/github/callback
```

Inject these values into the API process:

```text
APP_ENV=production
ORBIT_AUTH_ENABLED=true
ORBIT_PASSWORD_AUTH_ENABLED=false
ORBIT_AUTH_SECRET=<at-least-32-random-bytes>
ORBIT_PUBLIC_BASE_URL=https://YOUR_DOMAIN
GITHUB_OAUTH_CLIENT_ID=<oauth-app-client-id>
GITHUB_OAUTH_CLIENT_SECRET=<oauth-app-client-secret>
GITHUB_OAUTH_REDIRECT_URI=https://YOUR_DOMAIN/orbit-api/api/auth/github/callback
ORBIT_DEV_AUTH=false
```

Build the Web image without `NEXT_PUBLIC_ORBIT_DEV_SUBJECT`. Production startup rejects first-party
authentication when the public URL is not HTTPS.

The IP + port deploy script also has an explicit `github` mode for temporary OAuth integration
testing. It runs with `APP_ENV=preview`, disables the fixed development subject, and uses a
non-`Secure` cookie because the public URL is HTTP. This is not a production configuration: session
traffic can be intercepted on an untrusted network, so it must be replaced with HTTPS before the
site is shared with real users.

## Verification

Before enabling traffic, verify that `/api/auth/config` reports GitHub enabled and password auth
disabled, the callback returns to a same-origin `returnTo`, logout revokes the current database
session, and a second GitHub login reuses the same account rather than creating a duplicate.
