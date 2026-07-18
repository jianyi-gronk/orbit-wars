import json

from orbit_runtime.observability import (
    AlertPolicy,
    MetricRegistry,
    TraceContext,
    event_json,
    redact,
)


def test_sensitive_values_are_recursively_redacted_from_structured_logs() -> None:
    value = {
        "Authorization": "Bearer super-secret-token",
        "agent_key": "owk_prefix_actual-secret",
        "nested": {"sourceCode": "print('private')"},
        "message": "cookie orbit_session=session-value",
    }
    encoded = json.dumps(redact(value))

    assert "super-secret-token" not in encoded
    assert "actual-secret" not in encoded
    assert "print" not in encoded
    assert "session-value" not in encoded
    assert encoded.count("[REDACTED]") >= 4


def test_trace_spans_request_match_step_and_sandbox_without_payloads() -> None:
    trace = TraceContext("req-1", "match-1", 83, "sandbox-slot-0")
    event = event_json("agent.turn", trace, durationMs=18)

    assert json.loads(event) == {
        "durationMs": 18,
        "event": "agent.turn",
        "matchId": "match-1",
        "requestId": "req-1",
        "sandboxId": "sandbox-slot-0",
        "step": 83,
    }


def test_metrics_are_allowlisted_and_high_priority_signals_alert() -> None:
    registry = MetricRegistry()
    registry.add("turn_latency_ms", 12, controller="agent")
    registry.add("determinism_mismatch_total")
    registry.add("rating_duplicate_settlement_total")
    registry.add("sandbox_escape_signal_total")
    alerts = AlertPolicy().evaluate(registry.snapshot())

    assert {alert.name for alert in alerts} == {
        "determinism-mismatch",
        "duplicate-rating-settlement",
        "sandbox-escape-signal",
    }
