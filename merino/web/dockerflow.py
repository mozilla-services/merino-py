import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

router = APIRouter()


@router.get(
    "/__version__",
    tags=["__version__"],
    summary="Dockerflow: __version__",
)
async def version() -> JSONResponse:
    """
    Dockerflow: Query service version.
    """

    if not os.path.exists("version.json"):
        raise HTTPException(status_code=500, detail="Version file does not exist")

    with open("version.json") as f:
        version = json.load(f)
    return JSONResponse(content=jsonable_encoder(version))


@router.get(
    "/__heartbeat__", tags=["__heartbeat__"], summary="Dockerflow: __heartbeat__"
)
async def heartbeat() -> Response:
    """
    Dockerflow: Query service heartbeat. It returns an empty string in the response.
    """
    return Response(content="")


@router.get(
    "/__lbheartbeat__", tags=["__lbheartbeat__"], summary="Dockerflow: __lbheartbeat__"
)
async def lbheartbeat() -> Response:
    """
    Dockerflow: Query service heartbeat for load balancer. It returns an empty string in the
    response.
    """
    return Response(content="")
