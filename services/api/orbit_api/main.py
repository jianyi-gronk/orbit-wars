"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from orbit_runtime.infrastructure import DependencyCheckFailed, check_dependencies
from orbit_runtime.observability import MetricRegistry

from orbit_api.api.agent import router as agent_router
from orbit_api.api.fleets import router as fleets_router
from orbit_api.api.leaderboard import router as leaderboard_router
from orbit_api.api.matches import router as matches_router
from orbit_api.api.replays import router as replays_router
from orbit_api.api.session import router as session_router
from orbit_api.api.simulations import router as simulations_router
from orbit_api.api.ws_matches import router as ws_matches_router
from orbit_api.db.session import SessionLocal
from orbit_api.middleware.idempotency import IdempotencyMiddleware
from orbit_api.middleware.observability import ObservabilityMiddleware

app = FastAPI(title="Orbit Wars API", version="0.1.0")
metrics = MetricRegistry()
app.add_middleware(IdempotencyMiddleware, session_factory=SessionLocal)
app.add_middleware(ObservabilityMiddleware, registry=metrics)
app.include_router(agent_router)
app.include_router(fleets_router)
app.include_router(leaderboard_router)
app.include_router(matches_router)
app.include_router(replays_router)
app.include_router(simulations_router)
app.include_router(session_router)
app.include_router(ws_matches_router)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Report that the process is ready to receive requests."""
    return {"status": "ok", "service": "api"}


@app.get("/health/dependencies", tags=["operations"])
def dependency_health() -> dict[str, object]:
    """Report whether required stateful services are reachable."""
    try:
        dependencies = check_dependencies()
    except DependencyCheckFailed as error:
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "dependencies": error.failures},
        ) from error

    return {"status": "ok", "dependencies": dependencies}


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def operational_metrics() -> str:
    return metrics.prometheus()
