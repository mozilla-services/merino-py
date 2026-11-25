"""FastAPI application factory for merino-hook-eye.

The service has no API of its own. The HTTP server hosts the Dockerflow endpoints used by
Kubernetes probes, and the lifespan runs each enabled check in the background.
"""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute
from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry
from merino_common.routers import dockerflow

from merino_hook_eye.ccr import follower as ccr_follower
from merino_hook_eye.checks import RunningCheck
from merino_hook_eye.configs import settings

logger = logging.getLogger(__name__)

# Every check, by the name of its settings section, which has an `enabled` switch. Each value
# starts the check and stops it on exit.
CHECKS: dict[str, Callable[[], AbstractAsyncContextManager[RunningCheck]]] = {
    ccr_follower.NAME: ccr_follower.start,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Configure logging and Sentry, then run the enabled checks until shutdown."""
    configure_logging(
        log_format=settings.logging.format,
        level=settings.logging.level,
        can_propagate=settings.logging.can_propagate,
        current_env=settings.current_env,
        logger_name="merino_hook_eye",
    )
    configure_sentry(
        mode=settings.sentry.mode,
        dsn=settings.sentry.dsn,
        env=settings.sentry.env,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )
    enabled = [name for name in CHECKS if settings[name].enabled]
    if enabled:
        logger.info("Starting checks", extra={"checks": enabled})
    else:
        logger.warning("No checks are enabled; set `enabled` for at least one check")

    async with AsyncExitStack() as stack:
        app.state.checks = [await stack.enter_async_context(CHECKS[name]()) for name in enabled]
        yield


health_router = APIRouter()


@health_router.get("/__heartbeat__", tags=["__heartbeat__"], summary="Dockerflow: __heartbeat__")
async def heartbeat(request: Request) -> Response:
    """Dockerflow: report 503 when an enabled check's loop has died or stalled.

    This checks the monitor, not its targets: failed runs still count as progress, since
    restarting hook-eye wouldn't fix them. Each check's metrics report those.
    """
    checks: list[RunningCheck] = request.app.state.checks
    if not all(check.is_alive() for check in checks):
        return Response(status_code=503)
    return Response(content="")


def create_app() -> FastAPI:
    """Construct the FastAPI app."""
    app = FastAPI(title="merino-hook-eye", lifespan=lifespan)
    app.include_router(health_router)
    # The shared Dockerflow router, minus its always-200 heartbeat, which `health_router`
    # replaces.
    for route in dockerflow.router.routes:
        if not (isinstance(route, APIRoute) and route.path == "/__heartbeat__"):
            app.router.routes.append(route)
    return app
