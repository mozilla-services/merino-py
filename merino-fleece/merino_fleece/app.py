"""FastAPI application factory for merino-fleece."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry
from merino_common.routers import dockerflow

from merino_fleece.api.v1 import router as v1_router
from merino_fleece.configs import settings
from merino_fleece.message_handlers import search_terms
from merino_fleece.pii import (
    init_detector,
    init_executor,
    shutdown_detector,
    shutdown_executor,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize logging, Sentry, the SpaCy model, the PII detection thread pool, and
    the background search term sanitization handler.

    Shutdown order matters: the handler drains before the thread pool closes, since a
    batch sanitized during the drain still offloads NER to that pool.
    """
    configure_logging(
        log_format=settings.logging.format,
        level=settings.logging.level,
        can_propagate=settings.logging.can_propagate,
        current_env=settings.current_env,
        logger_name="merino_fleece",
    )
    configure_sentry(
        mode=settings.sentry.mode,
        dsn=settings.sentry.dsn,
        env=settings.sentry.env,
        traces_sample_rate=settings.sentry.traces_sample_rate,
    )
    init_detector()
    init_executor()
    await search_terms.start()
    try:
        yield
    finally:
        await search_terms.stop()
        shutdown_executor()
        shutdown_detector()


def create_app() -> FastAPI:
    """Construct the FastAPI app."""
    app = FastAPI(title="merino-fleece", lifespan=lifespan)
    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(dockerflow.router)
    return app
