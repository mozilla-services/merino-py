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
from merino.middleware import (
    featureflags,
    geolocation,
    logging as mw_logging,
    metrics,
    user_agent,
)
from merino.web import docs
from merino_common.routers import dockerflow

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
        "name": "widgets",
        "description": "APIs serving Firefox New Tab widgets.",
    },
]
_SUGGEST_TAG_NAMES = frozenset({"suggest", "providers"})
_WIDGETS_TAG_NAMES = frozenset({"widgets"})

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

    1. Add a RuntimeFeature and add it to the matching RuntimeMode entries in merino.runtime.
    2. Start the service here.
    3. Include the service's router in _include_routers.
    4. Add its OpenAPI tag metadata.
    5. Regenerate the committed OpenAPI schema (`moon run merino:openapi-export`).

    Dockerflow and the API docs stay enabled for every mode.
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
                logger_name="merino",
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

            suggest_enabled = mode_enables(runtime_mode, RuntimeFeature.SUGGEST)
            curated_enabled = mode_enables(runtime_mode, RuntimeFeature.CURATED_RECOMMENDATIONS)

            if suggest_enabled:
                await _start_suggest_services(cleanup_callbacks)

            # The manifest provider backs /manifest and the icons in curated recommendations.
            # Start it only one time, since each init_provider call schedules another resync cron.
            if suggest_enabled or curated_enabled:
                await _start_manifest_service()

            # curated_recommendations.init_provider() calls get_manifest_provider(), which raises a
            # ValueError until the manifest provider starts, and therefore this block runs after
            # _start_manifest_service().
            if curated_enabled:
                _start_curated_recommendations_services()

            if mode_enables(runtime_mode, RuntimeFeature.WIDGETS):
                await _start_rss_services(cleanup_callbacks)
                await _start_games_services()
                await _start_widget_services(cleanup_callbacks)

            # Started once for every mode, after the services, so circuit breakers in both the
            # regular and widget services are reported.
            _start_governance(cleanup_callbacks)

            yield
        finally:
            await _run_cleanup_callbacks(cleanup_callbacks)

    return runtime_lifespan


async def _start_suggest_services(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Initialize the Suggest providers and the search terms message handler.

    LoggingMiddleware submits search terms to the message handler only for suggest requests,
    so the handler starts with the `SUGGEST` feature.
    """
    from merino.message_handlers import search_terms
    from merino.providers import suggest

    await suggest.init_providers()
    cleanup_callbacks.append(suggest.shutdown_providers)

    if settings.message_handler.enabled:
        await search_terms.start()
        cleanup_callbacks.append(search_terms.stop)


async def _start_manifest_service() -> None:
    """Initialize the manifest provider. It has no shutdown work."""
    from merino.providers import manifest

    await manifest.init_provider()


def _start_curated_recommendations_services() -> None:
    """Initialize the curated recommendations provider. It has no shutdown work."""
    from merino import curated_recommendations

    curated_recommendations.init_provider()


async def _start_games_services() -> None:
    """Initialize game providers (e.g. Particle) for the widget API.

    Games providers have no shutdown work.
    """
    from merino.providers import games

    await games.init_providers()


async def _start_rss_services(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Initialize RSS providers (e.g. picture of the day) and register cleanup callbacks."""
    from merino.providers import rss

    await rss.init_providers()
    cleanup_callbacks.append(rss.shutdown_providers)


async def _start_widget_services(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Initialize only New Tab widget services and register cleanup callbacks."""
    from merino.providers import widgets

    await widgets.init_providers()
    cleanup_callbacks.append(widgets.shutdown_providers)


def _start_governance(cleanup_callbacks: list[CleanupCallback]) -> None:
    """Start service governance (e.g. circuit breaker metrics) and register cleanup."""
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
        # Every mode serves the committed ALL-mode schema instead, see merino.web.docs.
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
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

    if mode_enables(mode, RuntimeFeature.SUGGEST):
        enabled_tag_names.update(_SUGGEST_TAG_NAMES)

    if mode_enables(mode, RuntimeFeature.WIDGETS):
        enabled_tag_names.update(_WIDGETS_TAG_NAMES)

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
    app.include_router(docs.router)

    if mode_enables(mode, RuntimeFeature.SUGGEST):
        from merino.web import api_v1

        app.include_router(api_v1.router, prefix="/api/v1")

    if mode_enables(mode, RuntimeFeature.CURATED_RECOMMENDATIONS):
        from merino.web import api_v1_curated_recommendations

        app.include_router(api_v1_curated_recommendations.router, prefix="/api/v1")

    if mode_enables(mode, RuntimeFeature.WIDGETS):
        from merino.web import api_v1_widgets

        app.include_router(api_v1_widgets.router, prefix="/api/v1")


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    """This is used only for profiling.

    Start the profiling:
        $ python -m scalene apps/merino/merino/main.py
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True)
