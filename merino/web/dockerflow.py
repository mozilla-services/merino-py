"""Dockerflow Endpoints."""
import logging
import pathlib

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from merino.utils.version import fetch_app_version_file

router = APIRouter()
logger = logging.getLogger(__name__)
MERINO_PATH = pathlib.Path.cwd()


@router.get(
    "/__version__",
    tags=["__version__"],
    summary="Dockerflow: __version__",
)
async def version() -> JSONResponse:
    """Dockerflow: Query service version."""
    if not pathlib.Path("version.json").exists():
        raise HTTPException(status_code=500, detail="Version file does not exist")

    version_file = fetch_app_version_file(merino_root_path=MERINO_PATH)
    return JSONResponse(content=jsonable_encoder(version_file))


@router.get(
    "/__heartbeat__", tags=["__heartbeat__"], summary="Dockerflow: __heartbeat__"
)
async def heartbeat() -> Response:
    """Dockerflow: Query service heartbeat. It returns an empty string in the response."""
    return Response(content="")


@router.get(
    "/__lbheartbeat__", tags=["__lbheartbeat__"], summary="Dockerflow: __lbheartbeat__"
)
async def lbheartbeat() -> Response:
    """Dockerflow: Query service heartbeat for load balancer. It returns an empty string in the
    response.
    """
    return Response(content="")


@router.get("/__error__", tags=["__error__"], summary="Dockerflow: __error__")
async def test_error() -> Response:
    """Dockerflow: Return an API error to test service error handling."""
    logger.error("The __error__ endpoint was called")
    raise HTTPException(status_code=500, detail="")
