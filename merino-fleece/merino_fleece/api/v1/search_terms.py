"""Search terms submission endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import metrics
from pydantic import BaseModel

from merino_common.models.suggest_logging import SearchTermsSubmission
from merino_common.utils.async_batch_queue import AsyncBatchException
from merino_fleece.message_handlers.search_terms import MessageHandler, get_message_handler

logger = logging.getLogger(__name__)

_meter = metrics.get_meter("fleece")
_search_terms_received_counter = _meter.create_counter(
    name="api.search_terms.receive.count",
    description="Number of search terms received by the submission endpoint.",
)
_search_terms_rejected_counter = _meter.create_counter(
    name="api.search_terms.reject.count",
    description="Number of search terms rejected because they could not be queued.",
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
async def submit_search_terms(
    body: SearchTermsSubmission,
    handler: MessageHandler = Depends(get_message_handler),
) -> SearchTermsResponse:
    """Accept a batch of search terms and queue them for background sanitization.

    Sanitization happens off the request path, so a 201 means the terms were
    accepted for processing, not that they have been sanitized.

    Raises:
        HTTPException: 503 when the terms cannot be queued, so the submitter can
            back off rather than have its data silently dropped.
    """
    count = len(body.search_terms)
    _search_terms_received_counter.add(count)

    # Admit the whole submission or none of it. Enqueuing term by term and failing
    # partway would leave some terms queued while the submitter sees an error and
    # drops the batch, so neither side's accounting would be right.
    capacity = handler.remaining_capacity()
    if capacity < count:
        _search_terms_rejected_counter.add(count)
        logger.warning(
            "Rejected search term submission: insufficient queue capacity",
            extra={"submitted_count": count, "remaining_capacity": capacity},
        )
        raise HTTPException(status_code=503, detail="Search term queue is at capacity")

    for index, term in enumerate(body.search_terms):
        try:
            handler.put(term)
        except (AsyncBatchException, RuntimeError) as ex:
            # The capacity check above is exact for this request -- there is no await
            # between it and these puts -- but concurrent requests can pass it and
            # then compete for the same slots. Degrade to a partial enqueue rather
            # than a 500.
            _search_terms_rejected_counter.add(count - index)
            logger.warning(
                "Rejected search term submission: queue unavailable",
                extra={"submitted_count": count, "accepted_count": index, "error": str(ex)},
            )
            raise HTTPException(status_code=503, detail="Search term queue is unavailable") from ex

    return SearchTermsResponse(submitted=count)
