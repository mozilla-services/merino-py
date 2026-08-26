"""HTTP client for submitting search terms to merino-fleece for sanitization."""

import time

from httpx import AsyncClient, HTTPError, HTTPStatusError
from opentelemetry import metrics

from merino.configs import settings
from merino.message_handlers.search_terms.errors import FleeceError
from merino_common.models.suggest_logging import (
    SearchTermsSubmission,
    SuggestRequestParams,
)

_meter = metrics.get_meter("merino.message_handlers.search_terms.fleece")
_submit_duration_histogram = _meter.create_histogram(
    name="fleece.submit.duration",
    unit="s",
    description="Duration of search term submission requests to merino-fleece.",
)


class FleeceClient:
    """Client that submits batches of search terms to merino-fleece.

    Posts a ``SearchTermsSubmission`` (a batch of ``SuggestRequestParams``) to the
    merino-fleece ``/api/v1/search-terms`` endpoint.
    Args:
        http_client (AsyncClient): The async HTTP client used for submissions. Its
            ``base_url`` should be the merino-fleece service URL.
    """

    def __init__(self, http_client: AsyncClient) -> None:
        self.http_client = http_client
        self.search_terms_path = settings.fleece.search_terms_path

    async def submit(self, search_terms: list[SuggestRequestParams]) -> None:
        """Submit a batch of search terms to merino-fleece for sanitization.

        Args:
            search_terms (list[SuggestRequestParams]): The batch of search terms to submit.

        Raises:
            FleeceError: If the request fails (transport error, timeout, or non-2xx status).
        """
        submission = SearchTermsSubmission(search_terms=search_terms)
        start = time.perf_counter()
        outcome = "error"
        try:
            response = await self.http_client.post(
                self.search_terms_path, json=submission.model_dump()
            )
            response.raise_for_status()
        except HTTPError as ex:
            if isinstance(ex, HTTPStatusError):
                raise FleeceError(
                    "Fleece returned an unexpected status "
                    f"{ex.response.status_code} {ex.response.reason_phrase}"
                ) from ex
            raise FleeceError(f"Failed to submit search terms to Fleece: {ex}") from ex
        else:
            outcome = "success"
        finally:
            _submit_duration_histogram.record(time.perf_counter() - start, {"outcome": outcome})

    async def close(self) -> None:
        """Close the underlying HTTP client connections."""
        await self.http_client.aclose()
