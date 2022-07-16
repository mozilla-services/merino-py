from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from merino import providers
from merino.web import api_v1

app = FastAPI()


@app.on_event("startup")
async def startup_event() -> None:
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


app.include_router(api_v1.router, prefix="/api/v1")
