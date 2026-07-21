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

Preview mode uses a fixed development subject so the core loop can be exercised before OIDC and a
domain are configured. Do not treat this mode as a public multi-user production deployment.

GitHub login is intentionally not enabled by this IP preview script. It requires a domain, HTTPS,
and a GitHub OAuth App; see [`docs/authentication.md`](../../docs/authentication.md).
