"""A thin wrapper around the Remote Settings client."""
import asyncio
from asyncio import Task
from typing import Any, Literal, cast
from urllib.parse import urljoin

import httpx
import kinto_http
from pydantic import BaseModel

from merino.exceptions import BackendError
from merino.providers.adm.backends.protocol import SuggestionContent
from merino.utils.http_client import create_http_client

RS_CONNECT_TIMEOUT: float = 5.0

RecordType = Literal["data", "icon", "offline-expansion-data"]


class KintoSuggestion(BaseModel):
    """Class that holds Remote Settings suggestion attachment information."""

    id: int
    advertiser: str
    click_url: str | None = None
    full_keywords: list[list[Any]] = []
    iab_category: str
    icon: str
    impression_url: str | None = None
    keywords: list[str] = []
    title: str
    url: str


class RemoteSettingsError(BackendError):
    """Error during interaction with Remote Settings."""


class RemoteSettingsBackend:
    """Backend that connects to a live Remote Settings server."""

    kinto_http_client: kinto_http.AsyncClient

    def __init__(
        self, server: str | None, collection: str | None, bucket: str | None
    ) -> None:
        """Init the Remote Settings backend and create a new client.

        Args:
            server: the server address
            collection: the collection name
            bucket: the bucket name
        Raises:
            ValueError: If 'server', 'collection' or 'bucket' parameters are None or
                        empty.
        """
        if not server or not collection or not bucket:
            raise ValueError(
                "The Remote Settings 'server', 'collection' or 'bucket' parameters "
                "are not specified"
            )

        self.kinto_http_client = kinto_http.AsyncClient(
            server_url=server, bucket=bucket, collection=collection
        )

    async def fetch(self) -> SuggestionContent:
        """Fetch suggestions, keywords, and icons from Remote Settings.

        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        suggestions: dict[str, tuple[int, int]] = {}
        full_keywords: list[str] = []
        results: list[dict[str, Any]] = []
        icons: dict[str, str] = {}

        records: list[dict[str, Any]] = await self.get_records()

        attachment_host: str = await self.get_attachment_host()

        rs_suggestions: list[KintoSuggestion] = await self.get_suggestions(
            attachment_host, records
        )

        fkw_index = 0

        for suggestion in rs_suggestions:
            result_id = len(results)
            keywords = suggestion.keywords
            full_keywords_tuples = suggestion.full_keywords
            begin = 0
            for full_keyword, n in full_keywords_tuples:
                for query in keywords[begin : begin + n]:
                    # Note that for adM suggestions, each keyword can only be
                    # mapped to a single suggestion.
                    suggestions[query] = (result_id, fkw_index)
                begin += n
                full_keywords.append(full_keyword)
                fkw_index = len(full_keywords)
            results.append(suggestion.model_dump(exclude={"keywords", "full_keywords"}))
        icon_record = self.filter_records(record_type="icon", records=records)
        for icon in icon_record:
            id = icon["id"].replace("icon-", "")
            icons[id] = urljoin(
                base=attachment_host, url=icon["attachment"]["location"]
            )

        return SuggestionContent(
            suggestions=suggestions,
            full_keywords=full_keywords,
            results=results,
            icons=icons,
        )

    async def get_records(self) -> list[dict[str, Any]]:
        """Get records from the Remote Settings server.

        Returns:
            list[dict[str, Any]]: List of Remote Settings records
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        try:
            records: list[dict[str, Any]] = await self.kinto_http_client.get_records()
        except kinto_http.KintoException as error:
            raise RemoteSettingsError("Failed to get records") from error
        return records

    async def get_attachment_host(self) -> str:
        """Get the attachment host from the Remote Settings server.

        Returns:
            str: The attachment base URL
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        try:
            server_info: dict[str, Any] = await self.kinto_http_client.server_info()
        except kinto_http.KintoException as error:
            raise RemoteSettingsError("Failed to get server information") from error
        return cast(str, server_info["capabilities"]["attachments"]["base_url"])

    async def get_suggestions(
        self, attachment_host: str, records: list[dict[str, Any]]
    ) -> list[KintoSuggestion]:
        """Get suggestion data from all data records.

        Args:
            attachment_host: The attachment base URL
            records: List of Remote Settings records
        Returns:
            list[KintoSuggestion]: List of Remote Settings suggestion data
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        # Falls back to "data" records if "offline-expansion-data" records do not exist
        data_records: list[dict[str, Any]] = self.filter_records(
            "offline-expansion-data", records
        ) or self.filter_records("data", records)

        tasks: list[Task] = []
        try:
            async with asyncio.TaskGroup() as task_group:
                for record in data_records:
                    tasks.append(
                        task_group.create_task(
                            self.get_attachment(
                                url=urljoin(
                                    base=attachment_host,
                                    url=record["attachment"]["location"],
                                )
                            )
                        )
                    )
        except ExceptionGroup as error_group:
            raise RemoteSettingsError(error_group.exceptions)

        suggestions: list[KintoSuggestion] = []
        for task in tasks:
            suggestions.extend(await task)
        return suggestions

    async def get_attachment(self, url: str) -> list[KintoSuggestion]:
        """Get an attachment from the Remote Settings server for a given URL.

        Args:
            url: The attachment url
        Returns:
            list[KintoSuggestion]: List of Remote Settings suggestion data
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        async with create_http_client(
            connect_timeout=RS_CONNECT_TIMEOUT
        ) as httpx_client:
            try:
                response: httpx.Response = await httpx_client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise RemoteSettingsError("Failed to get attachment") from error
            # Dynamic Wikipedia provider supplies Wikipedia suggestions.
            # Excludes possible indexing of adM Wikipedia suggestions.
            return [
                KintoSuggestion(**data)
                for data in response.json()
                if data.get("advertiser", "") != "Wikipedia"
            ]

    def filter_records(
        self, record_type: RecordType, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter a list of Remote Settings records by record type.

        Args:
            record_type: Type of record
            records: List of Remote Settings records
        Returns:
            list[dict[str, Any]]: List of Remote Settings records filtered by type
        """
        return [record for record in records if record["type"] == record_type]
