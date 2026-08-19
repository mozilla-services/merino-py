"""Search terms submission endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry import metrics
from pydantic import BaseModel

from merino_common.models.suggest_logging import SearchTermsSubmission, SuggestRequestParams
from merino_common.utils.async_batch_queue import AsyncBatchException, AsyncBatchQueue
from merino_fleece.message_handlers.search_terms import get_queue

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
    queue: AsyncBatchQueue[SuggestRequestParams] | None = Depends(get_queue),
) -> SearchTermsResponse:
    """Accept a batch of search terms and queue them for background sanitization.

    Sanitization happens off the request path, so a 201 means the terms were
    accepted for processing, not that they have been sanitized.

    Raises:
        - HTTPException: 503 when the terms cannot be queued, normally indicating
          the service is overloaded and unable to accept more submissions, so the
          submitter can retry via other means such as the backup Pub/Sub channel
          rather than have its data silently dropped.
    """
    count = len(body.search_terms)
    _search_terms_received_counter.add(count)

    # Admit the whole submission or none of it. Enqueuing term by term and failing
    # partway would leave some terms queued while the submitter sees an error and
    # drops the batch, so neither side's accounting would be right. A missing queue
    # means background sanitization is not running at all, which is reported the same
    # way: no headroom, so the submitter falls back to the Pub/Sub backup channel.
    capacity = queue.remaining_capacity() if queue is not None else 0
    if queue is None or capacity < count:
        _search_terms_rejected_counter.add(count)
        logger.warning(
            "Rejected search term submission: insufficient queue capacity",
            extra={"submitted_count": count, "remaining_capacity": capacity},
        )
        raise HTTPException(status_code=503, detail="Search term queue is at capacity")

    for index, term in enumerate(body.search_terms):
        try:
            queue.put(term)
        except AsyncBatchException as ex:
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
