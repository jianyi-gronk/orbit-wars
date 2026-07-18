"""Request tracing, safe structured access logs, and HTTP metrics."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from orbit_runtime.observability import MetricRegistry, TraceContext, event_json
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("orbit.access")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, registry: MetricRegistry) -> None:
        super().__init__(app)
        self.registry = registry

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.trace = TraceContext(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        route = request.url.path
        self.registry.add(
            "http_requests_total", method=request.method, status=str(response.status_code)
        )
        self.registry.add("http_request_duration_ms", duration_ms, method=request.method)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            event_json(
                "http.request",
                request.state.trace,
                method=request.method,
                route=route,
                status=response.status_code,
                durationMs=round(duration_ms, 3),
            )
        )
        return response
