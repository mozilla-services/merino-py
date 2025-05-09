"""A thin wrapper around the Remote Settings client."""

import asyncio
from pympler import asizeof
from asyncio import Task
from collections import defaultdict
from typing import Any, Literal, cast
from urllib.parse import urljoin

import logging
import httpx
import kinto_http
from pydantic import BaseModel

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.adm.backends.protocol import (
    SuggestionContent,
    GlobalSuggestionContent,
)
from merino.utils.http_client import create_http_client
from merino.utils.icon_processor import IconProcessor

logger = logging.getLogger(__name__)

RS_CONNECT_TIMEOUT: float = 5.0
PLATFORMS = ["desktop", "tablet", "phone"]

RecordType = Literal["amp", "data", "icon"]


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


class ResultContext(BaseModel):
    """Class that hold result information for Suggestions."""

    core_suggestions_data: dict[int, dict[str, Any]] = {}
    overrides: dict[int, dict[str, Any]] = {}
    full_keywords: dict[str, list] = {}
    results: dict[str, tuple[int, int]] = {}
    icons_in_use: set = set()


class RemoteSettingsError(BackendError):
    """Error during interaction with Remote Settings."""


class RemoteSettingsBackend:
    """Backend that connects to a live Remote Settings server."""

    kinto_http_client: kinto_http.AsyncClient
    icon_processor: IconProcessor

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

    def process_keywords(self, suggestion: KintoSuggestion, platform: str, result_context: ResultContext) -> None:
        """Process keywords for suggestions."""
        keywords = suggestion.keywords
        result_context.icons_in_use.add(suggestion.icon)
        full_keywords_tuples = suggestion.full_keywords
        result = result_context.results
        if not result_context.full_keywords.get(platform):
            result_context.full_keywords[platform] = []
        full_keywords = result_context.full_keywords[platform]
        begin = 0
        fkw_index = 0
        for full_keyword, n in full_keywords_tuples:
            for query in keywords[begin : begin + n]:
                # Note that for adM suggestions, each keyword can only be
                # mapped to a single suggestion.
                result[query] = (suggestion.id, fkw_index)
                begin += n
                full_keywords.append(full_keyword)
                fkw_index = len(full_keywords)

    def find_diff_fields(
        self,
        desktop: KintoSuggestion | None,
        phone: KintoSuggestion | None,
        tablet: KintoSuggestion | None,
    ) -> set[str]:
        """Find field values that are different."""
        d = desktop.model_dump() if desktop else {}
        p = phone.model_dump() if phone else {}
        t = tablet.model_dump() if tablet else {}


        all_keys = set(d.keys()) | set(p.keys()) | set(t.keys())
        return {key for key in all_keys if len([d.get(key), p.get(key), t.get(key)]) > 1}

    def process_suggestions(
        self, suggestions: dict[str, list[KintoSuggestion]], result_context: ResultContext
    ) -> None:
        """Process a set of suggestions."""
        i, j, k = 0, 0, 0
        d_suggestions = suggestions["desktop"]
        t_suggestions = suggestions["tablet"]
        p_suggestions = suggestions["phone"]

        while i < len(d_suggestions) or j < len(t_suggestions) or k < len(p_suggestions):
            current_ids = []
            if i < len(d_suggestions):
                current_ids.append(d_suggestions[i].id)
            if j < len(t_suggestions):
                current_ids.append(t_suggestions[j].id)
            if k < len(p_suggestions):
                current_ids.append(p_suggestions[k].id)

            min_id = min(current_ids)

            # Gather the items that match the current min_id
            items = {
                "desktop": d_suggestions[i]
                if i < len(d_suggestions) and d_suggestions[i].id == min_id
                else None,
                "tablet": t_suggestions[j]
                if j < len(t_suggestions) and t_suggestions[j].id == min_id
                else None,
                "phone": p_suggestions[k]
                if k < len(p_suggestions) and p_suggestions[k].id == min_id
                else None,
            }

            diff_fields = self.find_diff_fields(items["desktop"], items["phone"], items["tablet"])

            # Choose first non-None item for core_suggestions_data
            primary_item = items.get("desktop") or items.get("tablet") or items.get("phone")
            if primary_item:
                result_context.core_suggestions_data[min_id] = primary_item.model_dump(
                    exclude={"keywords", "full_keywords", *diff_fields}
                )

            # Handle overrides and keyword processing
            for platform in ["desktop", "tablet", "phone"]:
                item = items[platform]
                if item:
                    if min_id not in result_context.overrides:
                        result_context.overrides[min_id] = {}
                    result_context.overrides[min_id][platform] = item.model_dump(
                        include=diff_fields
                    )
                    self.process_keywords(item, platform, result_context)

            # Increment indices for the items we processed
            if items["desktop"]:
                i += 1
            if items["tablet"]:
                j += 1
            if items["phone"]:
                k += 1

    async def fetch(self) -> GlobalSuggestionContent:
        """Fetch suggestions, keywords, and icons from Remote Settings.

        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        results: dict[str, Any] = {}
        icons: dict[str, str] = {}
        total_icons_in_use: set[str] = set()

        records: list[dict[str, Any]] = await self.get_records()
        attachment_host: str = await self.get_attachment_host()
        rs_suggestions: dict[str, dict[str, list[KintoSuggestion]]] = await self.get_suggestions(
            attachment_host, records
        )

        for country, c_suggestions in rs_suggestions.items():
            result_context: ResultContext = ResultContext()
            # sort platform specific suggestions by id
            for suggestion in c_suggestions.values():
                suggestion.sort(key=lambda x: x.id)

            self.process_suggestions(c_suggestions, result_context)

            # update to results
            total_icons_in_use.update(result_context.icons_in_use)
            results[country] = SuggestionContent(
                **result_context.model_dump(exclude={"icons_in_use"})
            )

        icon_record = self.filter_records(record_type="icon", records=records)

        icon_data = []
        tasks = []

        for icon in icon_record:
            id = icon["id"].replace("icon-", "")
            if id not in total_icons_in_use:
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
        print(f"{asizeof.asizeof(results["US"].core_suggestions_data)}")
        print(f"{asizeof.asizeof(results["US"].overrides)}")
        print(f"{asizeof.asizeof(results["US"].full_keywords)}")
        return GlobalSuggestionContent(suggestion_content=results, icons=icons)

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
    ) -> defaultdict[str, defaultdict[str, list[KintoSuggestion]]]:
        """Get suggestion data from all data records.

        Args:
            attachment_host: The attachment base URL
            records: List of Remote Settings records
        Returns:
            list[KintoSuggestion]: List of Remote Settings suggestion data
        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        data_records: list[dict[str, Any]] = self.filter_records("amp", records)

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
                            ),
                            name=f"{record["country"]}/{record["form_factor"]}",
                        )
                    )
        except ExceptionGroup as error_group:
            raise RemoteSettingsError(error_group.exceptions)

        suggestions: defaultdict[str, defaultdict[str, list[KintoSuggestion]]] = defaultdict(lambda: defaultdict(list))
        for task in tasks:
            result_suggestions = await task
            country, form_factor = task.get_name().split("/")
            suggestions[country][form_factor].extend(result_suggestions)
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
        async with create_http_client(connect_timeout=RS_CONNECT_TIMEOUT) as httpx_client:
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
            and potentially country and form_factor if applicable
        """
        filtered_records = []

        for record in records:
            if record.get("type") != record_type:
                continue

            if "country" in record and record["country"] not in settings.remote_settings.countries:
                continue

            filtered_records.append(record)
        return filtered_records
