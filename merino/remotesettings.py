"""A thin wrapper around the Remote Settings client."""
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import kinto_http

from merino.config import settings


class LiveBackend:
    """Backend that connects to a live Remote Settings server."""

    client: kinto_http.AsyncClient
    attachment_host: str = ""

    def __init__(self) -> None:
        """Init Remote Settings Client"""
        self.client = kinto_http.AsyncClient(server_url=settings.remote_settings.server)

    async def fetch_attachment_host(self) -> str:
        """Fetch the attachment host from the Remote Settings server."""
        server_info = await self.client.server_info()
        return cast(str, server_info["capabilities"]["attachments"]["base_url"])

    async def get(self, bucket: str, collection: str) -> list[dict[str, Any]]:
        """Get records from Remote Settings server.

        Args:
          - `collection`: the collection name
          -  `bucket`: the bucket name
        """
        return cast(
            list[dict[str, Any]],
            await self.client.get_records(collection=collection, bucket=bucket),
        )

    async def fetch_attachment(self, attachment_uri: str) -> httpx.Response:
        """Fetch an attachment from Remote Settings server for a given URI.

        Args:
          - `attachment_uri`: the URI of the attachment
        """
        if not self.attachment_host:
            self.attachment_host = await self.fetch_attachment_host()
        uri = urljoin(self.attachment_host, attachment_uri)
        async with httpx.AsyncClient() as client:
            return await client.get(uri)

    def get_icon_url(self, icon_uri: str) -> str:
        """Get the URL for an icon.

        Args:
          - `icon_uri`: a URI path for an icon stored on Remote Settings
        """
        return urljoin(self.attachment_host, icon_uri)
