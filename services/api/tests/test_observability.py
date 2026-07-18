import asyncio

import httpx
from orbit_api.main import app


def test_request_id_is_propagated_and_metrics_are_exported() -> None:
    async def run() -> tuple[httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health", headers={"X-Request-ID": "trace-test-1"})
            metrics = await client.get("/metrics")
            return response, metrics

    response, metrics = asyncio.run(run())
    assert response.headers["X-Request-ID"] == "trace-test-1"
    assert "http_requests_total" in metrics.text
    assert "http_request_duration_ms" in metrics.text
