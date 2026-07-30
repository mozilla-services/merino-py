"""PII / NER detection endpoint."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from opentelemetry import metrics
from pydantic import BaseModel, Field

from merino_fleece.configs import settings
from merino_fleece.pii import get_detector, get_executor
from merino_fleece.pii.detector import PiiDetector

QUERY_CHARACTER_MAX = settings.pii.query_character_max

_meter = metrics.get_meter("fleece")
_pii_detect_duration = _meter.create_histogram(
    name="api.pii_detect.duration",
    unit="ms",
    description="Duration of PII PERSON detection in milliseconds.",
)

router = APIRouter(tags=["pii"])


class PiiRequest(BaseModel):
    """Request body for the PII endpoint."""

    q: str = Field(
        min_length=1, max_length=QUERY_CHARACTER_MAX, description="Text to scan for PII."
    )


class PiiResponse(BaseModel):
    """Response for the PII endpoint."""

    pii: bool


async def _detect_pii(q: str, detector: PiiDetector, executor: ThreadPoolExecutor) -> PiiResponse:
    """Return whether `q` contains a PERSON named entity.

    SpaCy NER is CPU-bound and synchronous; it runs in the shared thread pool so
    it does not block the event loop and stall other concurrent requests.
    """
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    try:
        pii = await loop.run_in_executor(executor, detector.is_person, q)
    finally:
        _pii_detect_duration.record((loop.time() - started_at) * 1000)
    return PiiResponse(pii=pii)


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
    return await _detect_pii(body.q, detector, executor)


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
    return await _detect_pii(q, detector, executor)
