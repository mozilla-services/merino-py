"""PII / NER detection endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from merino_fleece.configs import settings
from merino_fleece.pii import get_detector
from merino_fleece.pii.detector import PiiDetector

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
def detect_pii(
    q: Annotated[
        str,
        Query(min_length=1, max_length=QUERY_CHARACTER_MAX, description="Text to scan for PII."),
    ],
    detector: PiiDetector = Depends(get_detector),
) -> PiiResponse:
    """Return whether `q` contains a PERSON named entity."""
    return PiiResponse(pii=detector.is_person(q))
