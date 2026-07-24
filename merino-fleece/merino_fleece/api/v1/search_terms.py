"""Search terms submission endpoint."""

from fastapi import APIRouter
from opentelemetry import metrics
from pydantic import BaseModel

from merino_common.models.suggest_logging import SearchTermsSubmission

_meter = metrics.get_meter("fleece")
_search_terms_received_counter = _meter.create_counter(
    name="api.search_terms.receive.count",
    description="Number of search terms received by the submission endpoint.",
)

router = APIRouter(tags=["search-terms"])


class SearchTermsResponse(BaseModel):
    """Response for the search-terms submission endpoint."""

    submitted: int


@router.post(
    "/search-terms",
    tags=["search-terms"],
    summary="Merino-fleece search terms submission endpoint",
    status_code=201,
    response_model=SearchTermsResponse,
)
async def submit_search_terms(body: SearchTermsSubmission) -> SearchTermsResponse:
    """Accept a batch of search terms for sanitization.

    The request body is validated by FastAPI and then discarded for now;
    sanitization and logging will be added as a follow-up.
    """
    count = len(body.search_terms)
    _search_terms_received_counter.add(count)

    return SearchTermsResponse(submitted=count)
