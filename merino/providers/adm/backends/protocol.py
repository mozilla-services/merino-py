"""Protocol for the AdM provider backends."""
from typing import Any, Protocol

import httpx


class AdmBackend(Protocol):
    """Protocol for a Remote Settings backend that this provider depends on.

    Note: This only defines the methods used by the provider. The actual backend
    might define additional methods and attributes which this provider doesn't
    directly depend on.
    """

    async def get(self) -> list[dict[str, Any]]:  # pragma: no cover
        """Get records from Remote Settings."""
        ...

    async def fetch_attachment(
        self, attachment_uri: str
    ) -> httpx.Response:  # pragma: no cover
        """Fetch the attachment for the given URI."""
        ...

    def get_icon_url(self, icon_uri: str) -> str:  # pragma: no cover
        """Get the icon URL for the given URI."""
        ...
