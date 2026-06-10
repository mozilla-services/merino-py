"""FastAPI application factory for merino-fleece."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from merino_common.app_configs.config_logging import configure_logging
from merino_common.app_configs.config_sentry import configure_sentry
from merino_common.routers import dockerflow

from merino_fleece.api.v1 import router as v1_router
from merino_fleece.configs import settings
from merino_fleece.pii import (
    init_detector,
    init_executor,
    shutdown_detector,
    shutdown_executor,
)
from merino_fleece.utils.metrics import configure_metrics


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize logging, Sentry, metrics, the SpaCy model, and the PII detection thread pool."""
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
    await configure_metrics()
    init_detector()
    init_executor()
    try:
        yield
    finally:
        shutdown_executor()
        shutdown_detector()


def create_app() -> FastAPI:
    """Construct the FastAPI app."""
    app = FastAPI(title="merino-fleece", lifespan=lifespan)
    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(dockerflow.router)
    return app
