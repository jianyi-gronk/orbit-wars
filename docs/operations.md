# Operations and privacy

## Trace and responsibility

Every HTTP response carries `X-Request-ID`. Worker events add `matchId`, logical `step`, and the isolated `sandboxId`; request bodies, commands, strategy source, tickets, cookies, and Agent credentials are never log fields. A failure can therefore be followed from API request to match/step/sandbox while preserving private strategy material.

Responsibility is explicit: `agent.*`, `human.*`, and rule-invalid commands are player/controller outcomes; recovery hash mismatch, queue/storage outage, and replay upload failure are platform outcomes; sandbox escape signals are security outcomes. A platform failure never becomes a rating result.

## Metrics and alerts

The `/metrics` endpoint exports an allowlisted process view. Production aggregation must collect HTTP volume/latency, queue wait, turn latency/late commands, sandbox CPU/memory/crashes, replay upload failures, rating settlements/duplicate signals, reconnects, determinism mismatches, and sandbox escape signals.

Critical pages fire on any determinism mismatch, duplicate rating settlement, or sandbox escape signal. Three replay upload failures in an evaluation interval are a warning. Alert rules are mirrored in `infra/observability/alerts.yml`.

## Rate limits

- Agent API: 60 requests/minute per key by default.
- Simulation creation: 10/minute independently per fleet and per key.
- Match tickets: five-minute, match/slot/fleet bound; they are not accepted outside the live route.
- Public replay delivery is intended to sit behind CDN request and bandwidth limits.

## Data retention

| Data                                      |                          Default | Disposal                                 |
| ----------------------------------------- | -------------------------------: | ---------------------------------------- |
| HTTP/worker structured logs               |                          14 days | delete from log store                    |
| Sandbox diagnostics (redacted/truncated)  |                           7 days | delete; never publish                    |
| Idempotency records                       |                         24 hours | scheduled database deletion              |
| Private uploaded strategy packages        |       account lifetime + 30 days | object delete after ownership hold       |
| Unpublished simulation candidate packages |                         24 hours | delete after simulation/retention window |
| Public match result and replay            | permanent unless policy takedown | tombstone public link, retain audit hash |
| Revoked Agent Key metadata                |                          90 days | delete digest and usage timestamps       |

Retention jobs emit counts only. Logs are scanned for `owk_`, bearer/JWT shapes, session cookies, private source markers, and match tickets before release.

## First response

For a critical alert: freeze rating finalization for affected matches, preserve redacted trace IDs and immutable replay/checkpoint hashes, rotate any suspected service credential, isolate the worker image, and follow `docs/runbooks/incident-response.md`. Do not copy user strategy packages into tickets or chat.
