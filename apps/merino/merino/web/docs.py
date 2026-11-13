"""API documentation routes backed by the committed OpenAPI schema.

Every runtime mode serves the same schema: the full ALL-mode API, generated at build time into
``merino/data/openapi.json``. This keeps the docs complete even when a deployment only serves a
subset of the API. Regenerate the schema with ``moon run merino:openapi-export``; CI fails
(``merino:openapi-check``) when the committed file is out of date.
"""

from functools import cache
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, Response

SCHEMA_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "openapi.json"
OPENAPI_URL = "/openapi.json"

router = APIRouter()


@cache
def load_schema() -> bytes:
    """Return the committed OpenAPI schema, read from disk once per process."""
    return SCHEMA_PATH.read_bytes()


@router.get(OPENAPI_URL, include_in_schema=False)
async def openapi() -> Response:
    """Serve the committed ALL-mode OpenAPI schema."""
    return Response(content=load_schema(), media_type="application/json")


@router.get("/docs", include_in_schema=False)
async def swagger_ui(request: Request) -> HTMLResponse:
    """Serve the Swagger UI for the committed OpenAPI schema."""
    return get_swagger_ui_html(
        openapi_url=OPENAPI_URL,
        title=f"{request.app.title} - Swagger UI",
    )
