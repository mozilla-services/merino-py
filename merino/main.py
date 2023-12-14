"""App startup point"""
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from merino import newtab
from merino import providers as suggest_providers
from merino.config_logging import configure_logging
from merino.config_sentry import configure_sentry
from merino.metrics import configure_metrics, get_metrics_client
from merino.middleware import featureflags, geolocation, logging, metrics, user_agent
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
    await suggest_providers.init_providers()
    await newtab.init_providers()
    yield
    # Shut down providers and clean up.
    await suggest_providers.shutdown_providers()
    await newtab.shutdown_providers()
    await get_metrics_client().close()


app = FastAPI(openapi_tags=tags_metadata, lifespan=lifespan)


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
app.add_middleware(user_agent.UserAgentMiddleware)
app.add_middleware(logging.LoggingMiddleware)

app.include_router(dockerflow.router)
app.include_router(api_v1.router, prefix="/api/v1")


if __name__ == "__main__":
    """This is used only for profiling.

    Start the profiling:
        $ python -m scalene merino/main.py
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True)
