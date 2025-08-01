"""A thin wrapper around the Remote Settings client."""

import asyncio
from asyncio import Task
from collections import defaultdict
from enum import Enum
from typing import Any, Literal, cast
from urllib.parse import urljoin

import logging
import httpx
import kinto_http
from moz_merino_ext.amp import AmpIndexManager
from pydantic import BaseModel

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.adm.backends.protocol import (
    SuggestionContent,
    SegmentType,
)
from merino.utils.http_client import create_http_client
from merino.utils.icon_processor import IconProcessor

logger = logging.getLogger(__name__)

RS_CONNECT_TIMEOUT: float = 5.0


RecordType = Literal["amp", "icon"]


class FormFactor(Enum):
    """Enum for form factor."""

    DESKTOP = 0
    PHONE = 1


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
    icon_processor: IconProcessor
    # A map to record the last modified timestamp for each "amp" type record.
    # The key stores the record ID and the value stores the "last_modified" field
    # generated by Remote Settings.
    last_modified_timestamps: dict[str, int]
    # Cache the latest suggestion content.
    suggestion_content: SuggestionContent

    def __init__(
        self,
        server: str | None,
        collection: str | None,
        bucket: str | None,
        icon_processor: IconProcessor,
    ) -> None:
        """Init the Remote Settings backend and create a new client.

        Args:
            server: the server address
            collection: the collection name
            bucket: the bucket name
            icon_processor: the icon processor for handling favicons
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

        self.icon_processor = icon_processor
        self.last_modified_timestamps = dict()
        self.suggestion_content = SuggestionContent(index_manager=AmpIndexManager(), icons={})  # type: ignore[no-untyped-call]

    def _should_skip(self, records: list[dict[str, Any]]) -> bool:
        """Check whether to skip processing records.
        This is an optimization for conditional record processing.

        Args:
            records: A list of "amp" records
        """
        for record in records:
            if (
                rid := record["id"]
            ) not in self.last_modified_timestamps or self.last_modified_timestamps[rid] < record[
                "last_modified"
            ]:
                return False
        return True

    async def fetch(self) -> SuggestionContent:
        """Fetch suggestions, keywords, and icons from Remote Settings.

        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        icons: dict[str, str] = {}
        icons_in_use: set[str] = set()

        records: list[dict[str, Any]] = await self.get_records()
        amp_records: list[dict[str, Any]] = self.filter_records("amp", records)

        if self._should_skip(amp_records):
            return self.suggestion_content

        attachment_host: str = await self.get_attachment_host()
        rs_suggestions: defaultdict[
            str, defaultdict[SegmentType, str]
        ] = await self.get_suggestions(attachment_host, amp_records)

        for country, c_suggestions in rs_suggestions.items():
            for segment, raw_suggestions in c_suggestions.items():
                idx_id = f"{country}/{segment}"
                try:
                    self.suggestion_content.index_manager.build(idx_id, raw_suggestions)
                    icons_in_use = icons_in_use.union(
                        self.suggestion_content.index_manager.list_icons(idx_id)
                    )
                except Exception as e:
                    logger.warning(
                        f"Unable to build index or get icons for {idx_id}",
                        extra={"error message": f"{e}"},
                    )

        icon_record = self.filter_records(record_type="icon", records=records)

        icon_data = []
        tasks = []

        for icon in icon_record:
            id = icon["id"].replace("icon-", "")
            if id not in icons_in_use:
                continue
            original_icon_url = urljoin(base=attachment_host, url=icon["attachment"]["location"])
            icon_data.append((id, original_icon_url))

        # Process all icons concurrently using TaskGroup
        try:
            async with asyncio.TaskGroup() as task_group:
                for _, url in icon_data:
                    tasks.append(task_group.create_task(self.icon_processor.process_icon_url(url)))
        except ExceptionGroup as eg:
            # If an unhandled exception occurs in TaskGroup
            logger.error(f"Errors during icon processing: {eg}")

        # Map results back to their IDs, handling any exceptions
        for (id, original_url), task in zip(icon_data, tasks):
            try:
                result = task.result()
                icons[id] = result
            except Exception as e:
                logger.error(f"Error processing icon {id}: {e}")
                icons[id] = original_url

        # Record the last modified timestamps for all processed "amp" records.
        for record in amp_records:
            self.last_modified_timestamps[record["id"]] = record["last_modified"]

        self.suggestion_content.icons = icons

        return self.suggestion_content

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

    def get_segment(self, record) -> SegmentType:
        """Compose segment, based on record division types."""
        form_factor = record["form_factor"].upper()
        return (FormFactor[form_factor].value,)

    async def get_suggestions(
        self, attachment_host: str, records: list[dict[str, Any]]
    ) -> defaultdict[str, defaultdict[SegmentType, str]]:
        """Get suggestion data from all data records.

        Args:
            attachment_host: The attachment base URL
            records: List of Remote Settings records of type "amp"
        Returns:
            list[KintoSuggestion]: List of Remote Settings suggestion data
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        tasks: list[
            tuple[
                str,
                SegmentType,
                Task,
            ]
        ] = []
        try:
            async with asyncio.TaskGroup() as task_group:
                for record in records:
                    segment = self.get_segment(record)
                    task: Task = task_group.create_task(
                        self.get_attachment_raw(
                            url=urljoin(
                                base=attachment_host,
                                url=record["attachment"]["location"],
                            )
                        )
                    )
                    tasks.append((record["country"], segment, task))
        except ExceptionGroup as error_group:
            raise RemoteSettingsError(error_group.exceptions)

        suggestions: defaultdict[str, defaultdict] = defaultdict(defaultdict)

        for country, segment, task in tasks:
            suggestions[country][segment] = await task
        return suggestions

    async def get_attachment_raw(self, url: str) -> str:
        """Get an attachment from the Remote Settings server for a given URL.

        Args:
            url: The attachment url
        Returns:
            list[KintoSuggestion]: List of Remote Settings suggestion data
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        async with create_http_client(connect_timeout=RS_CONNECT_TIMEOUT) as httpx_client:
            try:
                response: httpx.Response = await httpx_client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise RemoteSettingsError("Failed to get attachment") from error

            return response.text

    def filter_records(
        self, record_type: RecordType, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter a list of Remote Settings records by record type.

        Args:
            record_type: Type of record
            records: List of Remote Settings records
        Returns:
            list[dict[str, Any]]: List of Remote Settings records filtered by type
            and potentially country and form_factor if applicable
        """
        recs: list[dict[str, Any]] = [
            record for record in records if record["type"] == record_type
        ]
        if record_type == "amp":
            recs = [
                rec
                for rec in recs
                if rec["country"] in settings.remote_settings.countries
                and rec["form_factor"] in settings.remote_settings.form_factors
            ]

        return recs
