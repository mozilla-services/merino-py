"""Backend for the Google Suggest endpoint."""

import logging
import urllib.parse

from typing import cast

import aiodogstatsd

from httpx import AsyncClient, Response, HTTPStatusError
from merino.exceptions import BackendError
from merino.providers.suggest.google_suggest.backends.protocol import (
    GoogleSuggestResponse,
    SuggestRequest,
)


logger = logging.getLogger(__name__)


class GoogleSuggestBackend:
    """Backend that interfaces with Google Suggest endpoint."""

    http_client: AsyncClient
    url_suggest_path: str
    metrics_client: aiodogstatsd.Client

    def __init__(
        self,
        http_client: AsyncClient,
        url_suggest_path: str,
        metrics_client: aiodogstatsd.Client,
    ) -> None:
        """Initialize the backend."""
        self.http_client = http_client
        self.url_suggest_path = url_suggest_path
        self.metrics_client = metrics_client

    async def fetch(self, request: SuggestRequest) -> GoogleSuggestResponse:  # pragma: no cover
        """Fetch suggestions from the Google Suggest endpoint.

        `BackendError` will be raised if the request run into any issues.
        """
        # The original param string is URL encoded, the HTTP client wants a unencoded string.
        params = urllib.parse.unquote(request.params)

        try:
            with self.metrics_client.timeit("google_suggest.request.duration"):
                response: Response = await self.http_client.get(
                    self.url_suggest_path, params=params
                )

            response.raise_for_status()
        except HTTPStatusError as ex:
            logger.warning(
                f"Google Suggest request error: {ex.response.status_code} {ex.response.reason_phrase}"
            )
            self.metrics_client.increment(
                "google_suggest.request.failure", tags={"status_code": ex.response.status_code}
            )
            raise BackendError(f"Failed to fetch from Google Suggest: {ex}") from ex

        # Needed to explicitly cast because Merino will not process the response but
        # relay it as-is to the client.
        return cast(list, response.json())

    async def shutdown(self) -> None:
        """Close out the http client during shutdown."""
        await self.http_client.aclose()
