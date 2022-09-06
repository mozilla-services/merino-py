"""App startup point"""
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from merino import providers
from merino.config_logging import configure_logging
from merino.config_sentry import configure_sentry
from merino.metrics import configure_metrics, get_metrics_client
from merino.middleware import featureflags, geolocation, logging, metrics
from merino.web import api_v1, dockerflow

app = FastAPI()


@app.on_event("startup")
async def startup_configuration() -> None:
    """
    Set up various configurations such as logging.
    """
    configure_logging()
    configure_sentry()
    await configure_metrics()


@app.on_event("startup")
async def startup_providers() -> None:
    """Run tasks at application startup."""
    await providers.init_providers()


@app.on_event("shutdown")
async def shutdown() -> None:
    """
    Set up various configurations such as logging.
    """
    await get_metrics_client().close()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc) -> JSONResponse:
    """Use HTTP status code: 400 for all invalid requests."""
    return JSONResponse(
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
app.add_middleware(logging.LoggingMiddleware)

app.include_router(dockerflow.router)
app.include_router(api_v1.router, prefix="/api/v1")
