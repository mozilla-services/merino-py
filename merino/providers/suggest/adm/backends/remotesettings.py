"""A thin wrapper around the Remote Settings client."""
import ast
import asyncio
import json
from asyncio import Task
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
    SegmentTuple,
)
from merino.utils.http_client import create_http_client
from merino.utils.icon_processor import IconProcessor

logger = logging.getLogger(__name__)

RS_CONNECT_TIMEOUT: float = 5.0

RecordType = Literal["amp", "icon"]


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


class ResultContext(BaseModel):
    """Context object to help manage results."""

    core_suggestions_data: dict[int, Any] = {}
    variants: dict[int, dict[SegmentTuple, Any]] = {}
    full_keywords: dict[SegmentTuple, list] = {}
    results: dict[SegmentTuple, dict[str, tuple[int, int]]] = {}
    icons_in_use: set[str] = set()


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

    async def fetch(self) -> GlobalSuggestionContent:
        """Fetch suggestions, keywords, and icons from Remote Settings.

        Raises:
            RemoteSettingsError: Failed request to Remote Settings.
        """
        results: dict[str, Any] = {}
        icons: dict[str, str] = {}
        icons_in_use: set[str] = set()

        records: list[dict[str, Any]] = await self.get_records()
        attachment_host: str = await self.get_attachment_host()
        rs_suggestions: dict[
            str, dict[SegmentTuple, list[KintoSuggestion]]
        ] = await self.get_suggestions(attachment_host, records)

        for country, c_suggestions in rs_suggestions.items():
            result_context = ResultContext()
            self.process_suggestions(c_suggestions, result_context)
            # update processed suggestions to results
            icons_in_use.update(result_context.icons_in_use)
            results[country] = SuggestionContent(
                **result_context.model_dump(exclude={"icons_in_use"})
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
    ) -> dict[str, dict[SegmentTuple, list[KintoSuggestion]]]:
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
                            # denote segment dimensions of record to keep track of origin
                            name=f"{record["country"]}_{record["form_factor"]}",
                        )
                    )
        except ExceptionGroup as error_group:
            raise RemoteSettingsError(error_group.exceptions)

        suggestions: dict[str, dict] = {}
        for country in settings.remote_settings.countries:
            suggestions[country] = {}

        for task in tasks:
            result_suggestions = await task
            country, *segments = task.get_name().split("_")
            segment_key = tuple(segments)
            if segment_key not in suggestions[country]:
                suggestions[country][segment_key] = []
            suggestions[country][tuple(segments)].extend(result_suggestions)
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
        recs: list[dict[str, Any]] = [
            record for record in records if record["type"] == record_type
        ]
        if record_type == "amp":
            recs = [rec for rec in recs if rec["country"] in settings.remote_settings.countries]

        return recs

    def process_suggestions(
        self, suggestions: dict[SegmentTuple, list[KintoSuggestion]], result_context: ResultContext
    ) -> None:
        """TODO"""
        # sort segments by id for processing
        for segment_suggestions in suggestions.values():
            segment_suggestions.sort(key=lambda x: x.id)

        segments = suggestions.keys()
        indices = {s: 0 for s in segments}
        lengths = {s: len(suggestions[s]) for s in segments}

        while any(indices[s] < lengths[s] for s in segments):
            current_ids = []

            # get current suggestion id at current indices
            for segment in segments:
                idx = indices[segment]
                if idx < lengths[segment]:
                    current_ids.append(suggestions[segment][idx].id)

            min_id = min(current_ids)

            common_suggestions = {}
            for segment in segments:
                idx = indices[segment]
                if idx < lengths[segment] and suggestions[segment][idx].id == min_id:
                    common_suggestions[segment] = suggestions[segment][idx]

            diff_fields = self.find_diff_fields(list(common_suggestions.values()))

            # retrieve an arbitrary suggestion to get base fields
            primary_item = list(common_suggestions.values())[0]

            result_context.core_suggestions_data[min_id] = primary_item.model_dump(
                exclude={"keywords", "full_keywords", *diff_fields}
            )

            for segment, suggestion in common_suggestions.items():
                if min_id not in result_context.variants:
                    result_context.variants[min_id] = {}
                result_context.variants[min_id][segment] = suggestion.model_dump(
                    include=diff_fields
                )
                result_context.icons_in_use.add(suggestion.icon)
                self.process_keywords(suggestion, segment, result_context)

            for segment in segments:
                if segment in common_suggestions:
                    indices[segment] += 1
            #if min_id == 61:
            #    raise KeyError(f"core:{result_context.core_suggestions_data}\n variants:{result_context.variants}\n full_keywords:{result_context.full_keywords}\n result:{result_context.results}")

    def find_diff_fields(self, suggestions: list[KintoSuggestion]) -> set[str]:
        """Find all the fields that have different values"""
        data = [s.model_dump() for s in suggestions]
        all_keys = set().union(*(d.keys() for d in data))
        return {key for key in all_keys if len({str(d.get(key)) for d in data}) > 1}

    def process1_keywords(
        self, suggestion: KintoSuggestion, segment: SegmentTuple, result_context: ResultContext
    ) -> None:
        """Process keywords for suggestions."""
        keywords = suggestion.keywords
        full_keywords_tuples = suggestion.full_keywords
        result = result_context.results
        if not result_context.full_keywords.get(segment):
            result_context.full_keywords[segment] = []
        full_keywords = result_context.full_keywords[segment]
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

    def process_keywords(
        self, suggestion: KintoSuggestion, segment: SegmentTuple, result_context: ResultContext
    ) -> None:
        """Process keywords for suggestions."""
        keywords = suggestion.keywords
        full_keywords_tuples = suggestion.full_keywords
        result = result_context.results
        if not result_context.full_keywords.get(segment):
            result_context.full_keywords[segment] = []
            result[segment] = {}
            begin = 0
            fkw_index = 0
        else:
            begin = 0
            fkw_index = len(result_context.full_keywords[segment])-1

        full_keywords = result_context.full_keywords[segment]

        for full_keyword, n in full_keywords_tuples:
            for query in keywords[begin : begin + n]:
                try:
                    if full_keywords[fkw_index] == full_keyword:
                        result[segment][query] = (suggestion.id, fkw_index)
                    else:
                        full_keywords.append(full_keyword)
                        fkw_index = len(full_keywords) - 1
                except IndexError:
                        full_keywords.append(full_keyword)
                        fkw_index = len(full_keywords) - 1
            begin += n



