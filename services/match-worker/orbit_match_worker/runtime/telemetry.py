"""Process-local metrics exported by the worker adapter in production."""

from orbit_runtime.observability import MetricRegistry

worker_metrics = MetricRegistry()
