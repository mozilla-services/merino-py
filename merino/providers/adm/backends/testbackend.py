"""Test backend for the AdM provider."""
from typing import Any

import httpx


class TestBackend:
    """A test backend that always returns empty results for tests."""

    async def get(self) -> list[dict[str, Any]]:
        """Return fake records."""
        return []

    async def fetch_attachment(self, attachment_uri: str) -> httpx.Response:
        """Return a fake attachment for the given URI."""
        return httpx.Response(200, text="")

    def get_icon_url(self, icon_uri: str) -> str:
        """Return a fake icon URL for the given URI."""
        return ""
