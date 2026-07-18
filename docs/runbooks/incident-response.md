# Incident response

1. Declare severity and incident lead; record UTC start and alert name.
2. Contain: pause affected queue/finalization path. For sandbox escape signals, quarantine the worker pool and revoke its object-store credentials.
3. Correlate `requestId → matchId → step → sandboxId`; export only redacted structured events and immutable hashes.
4. Classify responsibility as platform, player/controller, or security. Platform failures remain unscored.
5. Recover from the last verified checkpoint, or mark the match failed if the state hash cannot reproduce.
6. Validate replay upload and exactly-once rating event before unpausing.
7. Rotate exposed credentials, notify affected owners, document scope and deletion actions.
8. Close only after metrics stabilize and a regression test covers the cause.
