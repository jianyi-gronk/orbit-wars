"""Small dependency-free observability primitives shared by API and workers."""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

SENSITIVE_FIELDS = frozenset(
    {
        "authorization",
        "cookie",
        "key",
        "secret",
        "secretdigest",
        "sourcecode",
        "packagebase64",
        "matchticket",
    }
)
_CREDENTIALS = re.compile(r"(?i)(bearer\s+\S+|owk_[A-Za-z0-9_\-]+|orbit_session=[^;\s]+)")
METRIC_NAMES = frozenset(
    {
        "http_requests_total",
        "http_request_duration_ms",
        "match_queue_wait_ms",
        "turn_latency_ms",
        "turn_late_total",
        "sandbox_cpu_ms",
        "sandbox_memory_bytes",
        "sandbox_crash_total",
        "replay_upload_failures_total",
        "rating_settlement_total",
        "rating_duplicate_settlement_total",
        "live_reconnect_total",
        "determinism_mismatch_total",
        "sandbox_escape_signal_total",
    }
)


def redact(value: Any, *, field: str = "") -> Any:
    normalized = field.replace("_", "").replace("-", "").lower()
    if normalized in SENSITIVE_FIELDS or normalized.endswith("secret"):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(key): redact(item, field=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _CREDENTIALS.sub("[REDACTED]", value)
    return value


@dataclass(frozen=True, slots=True)
class TraceContext:
    request_id: str
    match_id: str | None = None
    step: int | None = None
    sandbox_id: str | None = None

    def fields(self) -> dict[str, str | int]:
        values: dict[str, str | int | None] = {
            "requestId": self.request_id,
            "matchId": self.match_id,
            "step": self.step,
            "sandboxId": self.sandbox_id,
        }
        return {key: value for key, value in values.items() if value is not None}


class MetricRegistry:
    def __init__(self) -> None:
        self._values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._lock = threading.Lock()

    def add(self, name: str, value: float = 1, **labels: str) -> None:
        if name not in METRIC_NAMES:
            raise ValueError(f"unknown metric: {name}")
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._values[key] += value

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                name
                + (
                    "{" + ",".join(f'{key}="{value}"' for key, value in labels) + "}"
                    if labels
                    else ""
                ): amount
                for (name, labels), amount in self._values.items()
            }

    def prometheus(self) -> str:
        return (
            "\n".join(f"{name} {value}" for name, value in sorted(self.snapshot().items())) + "\n"
        )


@dataclass(frozen=True, slots=True)
class Alert:
    name: str
    severity: Literal["warning", "critical"]
    responsibility: Literal["platform", "player", "security"]


class AlertPolicy:
    def evaluate(self, metrics: dict[str, float]) -> list[Alert]:
        alerts: list[Alert] = []
        if metrics.get("determinism_mismatch_total", 0) > 0:
            alerts.append(Alert("determinism-mismatch", "critical", "platform"))
        if metrics.get("rating_duplicate_settlement_total", 0) > 0:
            alerts.append(Alert("duplicate-rating-settlement", "critical", "platform"))
        if metrics.get("sandbox_escape_signal_total", 0) > 0:
            alerts.append(Alert("sandbox-escape-signal", "critical", "security"))
        if metrics.get("replay_upload_failures_total", 0) >= 3:
            alerts.append(Alert("replay-upload-failures", "warning", "platform"))
        return alerts


def event_json(event: str, trace: TraceContext, **fields: Any) -> str:
    return json.dumps(
        redact({"event": event, **trace.fields(), **fields}),
        sort_keys=True,
        separators=(",", ":"),
    )
