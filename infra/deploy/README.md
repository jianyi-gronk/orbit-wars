# IP preview deployment

This deployment is intended for the no-domain preview stage. It exposes only the Next.js Web
process and keeps PostgreSQL, Redis, MinIO, and the API on the private container network.

```bash
ORBIT_PUBLIC_PORT=4000 bash infra/deploy/ip-preview.sh
```

The script creates only `orbit-*` containers, the `orbit-wars` container network, and persistent
data under `/opt/orbit-wars`. The web container uses the host network and listens on the selected
port; the API remains bound to `127.0.0.1:18000`. Secrets are generated once in
`/opt/orbit-wars/preview.env` with mode `0600` and are reused by later releases. Existing
PostgreSQL, Redis, and MinIO containers are reused during later releases so application updates do
not unnecessarily restart persistent dependencies.

Preview mode uses a fixed development subject by default so the core loop can be exercised before
OIDC and a domain are configured. Do not treat this mode as a public multi-user production
deployment.

For temporary OAuth integration testing only, put the GitHub OAuth credentials in `preview.env`,
configure the OAuth App callback as
`http://PUBLIC_IP:4000/orbit-api/api/auth/github/callback`, and run:

```bash
ORBIT_PREVIEW_AUTH_MODE=github \
ORBIT_PUBLIC_HOST=PUBLIC_IP \
ORBIT_PUBLIC_PORT=4000 \
bash infra/deploy/ip-preview.sh
```

This mode removes the fixed preview subject and disables password authentication. Because plain
HTTP cannot protect the session cookie in transit, use it only for short-lived testing and replace
it with the HTTPS production configuration in [`docs/authentication.md`](../../docs/authentication.md)
before inviting users.
