# Release, backup, and rollback

## Preflight

1. Use immutable API, Worker, Sandbox, and Web image digests; record the previous digests.
2. Load secrets from the deployment secret manager. Reject any `CHANGE_ME` value and require a 32+ character match-ticket secret.
3. Run `pnpm install --frozen-lockfile`, `pnpm check`, Web production build, and `npx @pureforge/smooth check`.
4. Run schema upgrade against a restored production-like backup, then `alembic current`.

## Deploy

1. Pause new ranked queue admission; allow running matches to finalize.
2. Take a PostgreSQL custom-format backup and record its SHA-256. Verify object-store versioning/retention.
3. Apply `alembic upgrade head`, deploy API/Worker, then Web. Sandbox image changes require the full isolation suite.
4. Smoke health/dependencies, one manual training, one Agent simulation, and one unscored synthetic ranked finalization.
5. Unpause admission and observe queue wait, turn latency, sandbox crashes, determinism, replay upload, and rating alerts.

## Database restore drill

Create a new empty database, restore with `pg_restore --clean --if-exists`, run `alembic current`, compare row counts/checksums for users, fleets, matches, participants, rating events, and replay metadata, then point a one-off API instance at the restored database for health/read smoke tests. Never overwrite the source database during a drill.

## Application rollback

If code fails but schema is backward compatible, pause admission and roll API/Worker/Web back to the recorded image digests. If the migration itself fails, restore the pre-deploy backup into a new database and switch the connection only after checksum and read-smoke validation. `alembic downgrade -1` is permitted only when the migration runbook marks it data-preserving and its automated round trip passed.

Running matches on an incompatible ruleset remain pinned to their original Worker image or are marked platform-failed and unscored; never replay them under changed rules silently.
