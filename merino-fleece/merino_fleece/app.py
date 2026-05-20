"""FastAPI application factory for merino-fleece."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry

from merino_fleece.api.v1 import router as v1_router
from merino_fleece.configs import settings
from merino_fleece.pii import init_detector, shutdown_detector


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize logging, Sentry, and load the SpaCy model on startup."""
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
    )
    init_detector()
    try:
        yield
    finally:
        shutdown_detector()


def create_app() -> FastAPI:
    """Construct the FastAPI app."""
    app = FastAPI(title="merino-fleece", lifespan=lifespan)
    app.include_router(v1_router, prefix="/api/v1")
    return app
