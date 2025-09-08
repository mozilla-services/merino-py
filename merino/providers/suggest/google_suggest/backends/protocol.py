"""Protocol for Google Suggest provider backends."""

from dataclasses import dataclass
from typing import Protocol

# An opaque type alias for Google Suggest API response.
# For a successful request to that endpoint, the response is a JSON array.
# We do not yet know the detailed response schema and Merino will return the
# response as-is to Firefox, so we will leave the content untyped for now
# (i.e. the array entry type is generic).
type GoogleSuggestResponse[T] = list[T]


@dataclass
class SuggestRequest:
    """Class that contains parameters needed to make a Google Suggest request."""

    # The query of the request. Note that the client is also provided this
    # via the `q` parameter in the following `params` parameter, but it could
    # be dropped from `params` in the future, so we keep it separately.
    query: str

    # A client provided URL encoded query param string that contains various
    # parameters needed for making the API request. Merino should relay this
    # over to the endpoint as-is.
    params: str


class GoogleSuggestBackendProtocol(Protocol):
    """Protocol for a Google Suggest backend.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def fetch(self, request: SuggestRequest) -> GoogleSuggestResponse:  # pragma: no cover
        """Fetch suggestions from the Google Suggest endpoint.

        `BackendError` will be raised if the request run into any issues.
        """
        ...

    async def shutdown(self) -> None:  # pragma: no cover
        """Close down any open connections."""
        ...
