"""PII / NER detection endpoint."""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from merino_fleece.configs import settings
from merino_fleece.pii import detect_person, get_detector, get_executor
from merino_fleece.pii.detector import PiiDetector

QUERY_CHARACTER_MAX = settings.pii.query_character_max

router = APIRouter(tags=["pii"])


class PiiRequest(BaseModel):
    """Request body for the PII endpoint."""

    q: str = Field(
        min_length=1, max_length=QUERY_CHARACTER_MAX, description="Text to scan for PII."
    )


class PiiResponse(BaseModel):
    """Response for the PII endpoint."""

    pii: bool


@router.post(
    "/pii",
    tags=["pii"],
    summary="Merino-fleece PII endpoint",
    response_model=PiiResponse,
)
async def detect_pii(
    body: PiiRequest,
    detector: PiiDetector = Depends(get_detector),
    executor: ThreadPoolExecutor = Depends(get_executor),
) -> PiiResponse:
    """Return whether `body.q` contains a PERSON named entity."""
    return PiiResponse(pii=await detect_person(body.q, detector, executor))


@router.get(
    "/pii",
    tags=["pii"],
    summary="Merino-fleece PII endpoint (deprecated; use POST)",
    response_model=PiiResponse,
    deprecated=True,
)
async def detect_pii_get(
    q: Annotated[
        str,
        Query(min_length=1, max_length=QUERY_CHARACTER_MAX, description="Text to scan for PII."),
    ],
    detector: PiiDetector = Depends(get_detector),
    executor: ThreadPoolExecutor = Depends(get_executor),
) -> PiiResponse:
    """Return whether `q` contains a PERSON named entity.

    Retained for backwards compatibility; prefer the POST endpoint.
    """
    return PiiResponse(pii=await detect_person(q, detector, executor))
