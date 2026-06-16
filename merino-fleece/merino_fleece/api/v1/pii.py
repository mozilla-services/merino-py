"""PII / NER detection endpoint."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from merino_fleece.configs import settings
from merino_fleece.pii import get_detector, get_executor
from merino_fleece.pii.detector import PiiDetector
from merino_fleece.utils.metrics import get_metrics_client

QUERY_CHARACTER_MAX = settings.pii.query_character_max

router = APIRouter(tags=["pii"])


class PiiResponse(BaseModel):
    """Response for the PII endpoint."""

    pii: bool


@router.get(
    "/pii",
    tags=["pii"],
    summary="Merino-fleece PII endpoint",
    response_model=PiiResponse,
)
async def detect_pii(
    q: Annotated[
        str,
        Query(min_length=1, max_length=QUERY_CHARACTER_MAX, description="Text to scan for PII."),
    ],
    detector: PiiDetector = Depends(get_detector),
    executor: ThreadPoolExecutor = Depends(get_executor),
) -> PiiResponse:
    """Return whether `q` contains a PERSON named entity.

    SpaCy NER is CPU-bound and synchronous; it runs in the shared thread pool so
    it does not block the event loop and stall other concurrent requests.
    """
    loop = asyncio.get_running_loop()
    with get_metrics_client().timeit("pii.detect_duration"):
        pii = await loop.run_in_executor(executor, detector.is_person, q)
    return PiiResponse(pii=pii)
