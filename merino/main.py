"""App startup point"""

import inspect
import logging

from collections.abc import Callable
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, status, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from merino.runtime import (
    RuntimeFeature,
    RuntimeMode,
    coerce_runtime_mode,
    get_runtime_mode,
    mode_enables,
)
from merino.configs import settings
from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry
from merino.utils.metrics import configure_metrics, get_metrics_client
from merino.middleware import featureflags, geolocation, logging as mw_logging, metrics, user_agent
from merino.web import dockerflow

tags_metadata = [
    {
        "name": "suggest",
        "description": "Main search API to query Firefox Suggest.",
    },
    {
        "name": "providers",
        "description": "Get a list of Firefox Suggest providers and their availability.",
    },
    {
        "name": "wcs",
        "description": "World Cup Soccer match data for the New Tab widget.",
    },
]
_REGULAR_API_TAG_NAMES = frozenset({"suggest", "providers"})
_WCS_API_TAG_NAMES = frozenset({"wcs"})

logger = logging.getLogger(__name__)
CleanupCallback = Callable[[], object]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up various configurations at startup and handle shutdown clean up.
    See lifespan events in fastAPI docs https://fastapi.tiangolo.com/advanced/events/
    """
    async with create_lifespan(get_runtime_mode())(app):
        yield


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Use HTTP status code: 400 for all invalid requests."""
    if not isinstance(exc, RequestValidationError):
        raise exc

    # `exe.errors()` is intentionally omitted in the log to avoid log excessively
    # large error messages.
    logger.warning(f"HTTP 400: request validation error for path: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


def create_lifespan(mode: RuntimeMode | str):
    """Build startup and shutdown work for a runtime mode.

    To wire a new service into the main app:
    add a RuntimeFeature, opt it into the right RuntimeMode values, start it here,
    include its router in _include_routers, and add its OpenAPI tag metadata.
    Dockerflow stays enabled for every mode.
    """
    runtime_mode = coerce_runtime_mode(mode)

    @asynccontextmanager
    async def runtime_lifespan(app: FastAPI):
        cleanup_callbacks: list[CleanupCallback] = []
        try:
            configure_logging(
                log_format=settings.logging.format,
                level=settings.logging.level,
                can_propagate=settings.logging.can_propagate,
                current_env=settings.current_env,
            )
            configure_sentry(
                mode=settings.sentry.mode,
                dsn=settings.sentry.dsn,
                env=settings.sentry.env,
                traces_sample_rate=settings.sentry.traces_sample_rate,
                default_tags={"server_region": settings.gcp.region},
            )
            await configure_metrics()
            cleanup_callbacks.append(_close_metrics_client)

            if mode_enables(runtime_mode, RuntimeFeature.REGULAR_API):
                await _start_regular_services(cleanup_callbacks)

            if mode_enables(runtime_mode, RuntimeFeature.WCS_API):
                await _start_wcs_services(cleanup_callbacks)

            if mode_enables(runtime_mode, RuntimeFeature.REGULAR_API):
                _start_governance(cleanup_callbacks)

            yield
        finally:
            await _run_cleanup_callbacks(cleanup_callbacks)

    return runtime_lifespan


async def _start_regular_services(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Initialize regular Merino services and register cleanup callbacks."""
    from merino import curated_recommendations
    from merino.providers import games, manifest, rss, suggest

    await suggest.init_providers()
    cleanup_callbacks.append(suggest.shutdown_providers)

    await manifest.init_provider()

    await rss.init_providers()
    cleanup_callbacks.append(rss.shutdown_providers)

    curated_recommendations.init_provider()
    await games.init_providers()


async def _start_wcs_services(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Initialize World Cup widget services and register cleanup callbacks."""
    from merino.providers import wcs

    await wcs.init_provider()
    cleanup_callbacks.append(wcs.shutdown_provider)


def _start_governance(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Start regular service governance and register cleanup."""
    from merino import governance

    governance.start()
    cleanup_callbacks.append(governance.shutdown)


async def _run_cleanup_callbacks(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Run cleanup callbacks in reverse startup order."""
    for cleanup in reversed(cleanup_callbacks):
        result = cleanup()
        if inspect.isawaitable(result):
            await result


async def _close_metrics_client() -> None:
    """Close the shared metrics client."""
    await get_metrics_client().close()


def create_app(mode: RuntimeMode | str | None = None) -> FastAPI:
    """Create the FastAPI application for a runtime mode."""
    runtime_mode = get_runtime_mode() if mode is None else coerce_runtime_mode(mode)
    app = FastAPI(
        openapi_tags=_get_tags_metadata(runtime_mode),
        lifespan=create_lifespan(runtime_mode),
        default_response_class=JSONResponse,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    _add_middleware(app)
    _include_routers(app, runtime_mode)
    return app


def _get_tags_metadata(mode: RuntimeMode) -> list[dict[str, str]]:
    """Return OpenAPI tag metadata for enabled feature groups."""
    enabled_tag_names: set[str] = set()

    if mode_enables(mode, RuntimeFeature.REGULAR_API):
        enabled_tag_names.update(_REGULAR_API_TAG_NAMES)

    if mode_enables(mode, RuntimeFeature.WCS_API):
        enabled_tag_names.update(_WCS_API_TAG_NAMES)

    return [tag for tag in tags_metadata if tag["name"] in enabled_tag_names]


def _add_middleware(app: FastAPI) -> None:
    """Register the historical app-wide middleware stack for every runtime mode."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS", "HEAD"],
    )
    app.add_middleware(metrics.MetricsMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(featureflags.FeatureFlagsMiddleware)
    app.add_middleware(geolocation.GeolocationMiddleware)
    app.add_middleware(user_agent.UserAgentMiddleware)
    app.add_middleware(mw_logging.LoggingMiddleware)


def _include_routers(app: FastAPI, mode: RuntimeMode) -> None:
    """Include routers enabled for a runtime mode."""
    app.include_router(dockerflow.router)

    if mode_enables(mode, RuntimeFeature.REGULAR_API):
        from merino.web import api_v1

        app.include_router(api_v1.router, prefix="/api/v1")

    if mode_enables(mode, RuntimeFeature.WCS_API):
        from merino.web import api_v1_wcs

        app.include_router(api_v1_wcs.router, prefix="/api/v1")


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    """This is used only for profiling.

    Start the profiling:
        $ python -m scalene merino/main.py
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True)
