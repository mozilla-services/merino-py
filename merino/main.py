from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from merino import providers
from merino.config_logging import configure_logging
from merino.middleware import logging
from merino.web import api_v1, dockerflow

app = FastAPI()


@app.on_event("startup")
def startup_configuration() -> None:
    """
    Set up various configurations such as logging.
    """
    configure_logging()


@app.on_event("startup")
async def startup_providers() -> None:
    """
    Run tasks at application startup.
    """
    await providers.init_providers()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc) -> JSONResponse:
    """
    Use HTTP status code: 400 for all invalid requests.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder({"detail": exc.errors()}),
    )


app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(logging.LoggingMiddleware)

app.include_router(dockerflow.router)
app.include_router(api_v1.router, prefix="/api/v1")

cors_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"http://localhost:^([1-9][0-9]{0,3}|[1-5][0-9]{4}"
    / r"|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    max_age=3600,
)
