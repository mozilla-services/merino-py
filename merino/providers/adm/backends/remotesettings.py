"""A thin wrapper around the Remote Settings client."""
from asyncio import as_completed
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import kinto_http

from merino.providers.adm.backends.protocol import SuggestionContent


class RemoteSettingsBackend:
    """Backend that connects to a live Remote Settings server."""

    attachment_host: str = ""
    bucket: str
    client: kinto_http.AsyncClient
    collection: str

    def __init__(self, server: str, collection: str, bucket: str) -> None:
        """Init the Remote Settings backend and create a new client.

        Args:
          - `server`: the server address
          - `collection`: the collection name
          - `bucket`: the bucket name
        Raises:
            ValueError: If 'server', 'collection' or 'bucket' parameters are None or
                        empty.
        """
        if not server or not collection or not bucket:
            raise ValueError(
                "The Remote Settings 'server', 'collection' or 'bucket' parameters "
                "are not specified"
            )

        self.client = kinto_http.AsyncClient(server_url=server)
        self.collection = collection
        self.bucket = bucket

    async def fetch_attachment_host(self) -> str:
        """Fetch the attachment host from the Remote Settings server."""
        server_info = await self.client.server_info()
        return cast(str, server_info["capabilities"]["attachments"]["base_url"])

    async def get(self) -> list[dict[str, Any]]:
        """Get records from the Remote Settings server."""
        return cast(
            list[dict[str, Any]],
            await self.client.get_records(
                collection=self.collection, bucket=self.bucket
            ),
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

    async def fetch(self) -> SuggestionContent:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        suggestions: dict[str, tuple[int, int]] = {}
        full_keywords: list[str] = []
        results: list[dict[str, Any]] = []
        icons: dict[int, str] = {}

        suggest_settings = await self.get()

        # Falls back to "data" records if "offline-expansion-data" records do not exist
        records = [
            record
            for record in suggest_settings
            if record["type"] == "offline-expansion-data"
        ] or [record for record in suggest_settings if record["type"] == "data"]

        fetch_tasks = [
            self.fetch_attachment(item["attachment"]["location"]) for item in records
        ]
        fkw_index = 0
        for done_task in as_completed(fetch_tasks):
            res = await done_task

            for suggestion in res.json():
                result_id = len(results)
                keywords = suggestion.pop("keywords", [])
                full_keywords_tuples = suggestion.pop("full_keywords", [])
                begin = 0
                for full_keyword, n in full_keywords_tuples:
                    for query in keywords[begin : begin + n]:
                        # Note that for adM suggestions, each keyword can only be
                        # mapped to a single suggestion.
                        suggestions[query] = (result_id, fkw_index)
                    begin += n
                    full_keywords.append(full_keyword)
                    fkw_index = len(full_keywords)
                results.append(suggestion)
        icon_record = [
            record for record in suggest_settings if record["type"] == "icon"
        ]
        for icon in icon_record:
            id = int(icon["id"].replace("icon-", ""))
            icons[id] = self.get_icon_url(icon["attachment"]["location"])

        return SuggestionContent(
            suggestions=suggestions,
            full_keywords=full_keywords,
            results=results,
            icons=icons,
        )
