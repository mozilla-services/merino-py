from fastapi import FastAPI

from merino import providers
from merino.web import api_v1

app = FastAPI()


@app.on_event("startup")
async def startup_event() -> None:
    await providers.init_providers()


app.include_router(api_v1.router, prefix="/api/v1")
