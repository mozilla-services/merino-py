"""App startup point"""

import logging

from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, status, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from merino import curated_recommendations, governance
from merino.configs.app_configs.config_logging import configure_logging
from merino.configs.app_configs.config_sentry import configure_sentry
from merino.providers import suggest, manifest
from merino.utils.metrics import configure_metrics, get_metrics_client
from merino.middleware import featureflags, geolocation, logging as mw_logging, metrics, user_agent
from merino.web import api_v1, dockerflow

tags_metadata = [
    {
        "name": "suggest",
        "description": "Main search API to query Firefox Suggest.",
    },
    {
        "name": "providers",
        "description": "Get a list of Firefox Suggest providers and their availability.",
    },
]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up various configurations at startup and handle shutdown clean up.
    See lifespan events in fastAPI docs https://fastapi.tiangolo.com/advanced/events/
    """
    # Setup methods run before `yield` and cleanup methods after.
    # Load sentry and logging, init providers.
    configure_logging()
    configure_sentry()
    await configure_metrics()
    await suggest.init_providers()
    await manifest.init_provider()
    curated_recommendations.init_provider()
    governance.start()
    yield
    governance.shutdown()
    # Shut down providers and clean up.
    await suggest.shutdown_providers()
    await get_metrics_client().close()


app = FastAPI(openapi_tags=tags_metadata, lifespan=lifespan, default_response_class=ORJSONResponse)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> ORJSONResponse:
    """Use HTTP status code: 400 for all invalid requests."""
    # `exe.errors()` is intentionally omitted in the log to avoid log excessively
    # large error messages.
    logger.warning(f"HTTP 400: request validation error for path: {request.url.path}")
    return ORJSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


# Note: the order of the following middleware registration matters.
# Specifically, `LoggingMiddleware` should be added after `CorrelationIdMiddleware` and
# `GeolocationMiddleware`.
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

app.include_router(dockerflow.router)
app.include_router(api_v1.router, prefix="/api/v1")


if __name__ == "__main__":  # pragma: no cover
    """This is used only for profiling.

    Start the profiling:
        $ python -m scalene merino/main.py
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True)
