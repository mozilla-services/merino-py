"""Backend that fetches sponsored suggestion data from the MARS API."""

import asyncio
from asyncio import Task
from collections import defaultdict
import json
import logging
import time
from urllib.parse import urljoin

import aiodogstatsd
import httpx
from moz_merino_ext.amp import AmpIndexManager

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.adm.backends.protocol import (
    FormFactor,
    SegmentType,
    SuggestionContent,
)
from merino.utils.http_client import create_http_client
from merino.utils.icon_processor import IconProcessor

logger = logging.getLogger(__name__)


class MarsError(BackendError):
    """Error during interaction with the MARS API."""


class MarsBackend:
    """Backend that connects to the MARS API for sponsored suggestions."""

    icon_processor: IconProcessor
    base_url: str
    suggestion_url_path: str
    http_client: httpx.AsyncClient
    metrics_client: aiodogstatsd.Client
    # Cache the latest suggestion content.
    suggestion_content: SuggestionContent
    # ETag tracking per segment for conditional fetching.
    etags: dict[str, str]
    # Timestamp of the last successful 200-with-data response.
    last_new_data_at: float

    def __init__(
        self,
        base_url: str,
        icon_processor: IconProcessor,
        metrics_client: aiodogstatsd.Client,
        connect_timeout: float,
        request_timeout: float,
        suggestion_url_path: str = "data",
    ) -> None:
        """Initialize the MARS backend.

        Args:
            base_url: The base URL for the MARS API.
            icon_processor: The icon processor for handling favicons.
            metrics_client: The StatsD metrics client.
            connect_timeout: Timeout in seconds for establishing a connection.
            request_timeout: Timeout in seconds for a request.
            suggestion_url_path: The URL path for fetching suggestions.

        Raises:
            ValueError: If base_url is empty.
        """
        if not base_url:
            raise ValueError("The MARS 'base_url' parameter is not specified")

        self.base_url = base_url
        self.suggestion_url_path = suggestion_url_path
        self.icon_processor = icon_processor
        self.metrics_client = metrics_client
        self.http_client = create_http_client(
            connect_timeout=connect_timeout,
            request_timeout=request_timeout,
        )
        self.suggestion_content = SuggestionContent(
            index_manager=AmpIndexManager(),  # type: ignore[no-untyped-call]
            icons={},
        )
        self.etags = {}
        self.last_new_data_at = 0.0

    def _emit_index_metrics(self, idx_id: str, index_label: str) -> None:
        """Emit gauge metrics for the amp index after a successful build."""
        stats = self.suggestion_content.index_manager.stats(idx_id)
        tags = {"index": index_label}
        for key, value in stats.items():
            self.metrics_client.gauge(f"amp.index.{key}", value=value, tags=tags)

    def get_segment(self, form_factor_str: str) -> SegmentType:
        """Compose segment from a form factor string.

        Mirrors ``RemoteSettingsBackend.get_segment`` which reads the form
        factor from a Kinto record.
        """
        return (FormFactor[form_factor_str.upper()].value,)

    async def fetch(self) -> SuggestionContent:
        """Fetch suggestions and icons from the MARS API.

        Builds segments, fetches suggestion data concurrently, builds
        indexes, then processes icons.

        Raises:
            MarsError: Failed request to the MARS API.
        """
        icons: dict[str, str] = {}
        icons_in_use: set[str] = set()

        # Deduplicate config lists (defensive against dynaconf_merge).
        countries: list[str] = list(dict.fromkeys(settings.mars.countries))
        form_factors: list[str] = list(dict.fromkeys(settings.mars.form_factors))

        # Build the list of segments.
        segments: list[tuple[str, SegmentType, str, str]] = []
        segment_labels: dict[SegmentType, str] = {}
        for country in countries:
            for form_factor in form_factors:
                segment = self.get_segment(form_factor)
                idx_id = f"{country}/{segment}"
                segments.append((country, segment, form_factor, idx_id))
                segment_labels[segment] = form_factor

        # Fetch suggestion data for all segments concurrently.
        mars_suggestions: defaultdict[str, dict[SegmentType, str]] = await self.get_suggestions(
            segments
        )

        # All segments returned 304 Not Modified — return cached content.
        if not mars_suggestions:
            return self.suggestion_content

        for country, c_suggestions in mars_suggestions.items():
            for segment, raw_suggestions in c_suggestions.items():
                idx_id = f"{country}/{segment}"
                try:
                    self.suggestion_content.index_manager.build(idx_id, raw_suggestions)
                    icons_in_use = icons_in_use.union(
                        self.suggestion_content.index_manager.list_icons(idx_id)
                    )
                    index_label = f"{country}/{segment_labels.get(segment, str(segment))}"
                    self._emit_index_metrics(idx_id, index_label)
                except Exception as e:
                    logger.warning(
                        f"Unable to build index or get icons for {idx_id}",
                        extra={"error message": f"{e}"},
                    )

        # Process icons concurrently. MARS provides full CDN URLs in the
        # icon field, so we use them directly for re-hosting.
        icon_data: list[tuple[str, str]] = []
        tasks: list[Task[str]] = []

        for icon_url in icons_in_use:
            icon_data.append((icon_url, icon_url))

        try:
            async with asyncio.TaskGroup() as task_group:
                for _, url in icon_data:
                    tasks.append(task_group.create_task(self.icon_processor.process_icon_url(url)))
        except ExceptionGroup as eg:
            logger.error(f"Errors during icon processing: {eg}")

        for (icon_id, original_url), task in zip(icon_data, tasks):
            try:
                result = task.result()
                icons[icon_id] = result
            except Exception as e:
                logger.error(f"Error processing icon {icon_id}: {e}")
                icons[icon_id] = original_url

        self.suggestion_content.icons.update(icons)

        return self.suggestion_content

    async def get_suggestions(
        self, segments: list[tuple[str, SegmentType, str, str]]
    ) -> defaultdict[str, dict[SegmentType, str]]:
        """Get suggestion data from all segments concurrently.

        Iterate over config-driven country x form_factor segments.

        Args:
            segments: List of (country, segment, form_factor, idx_id) tuples.

        Returns:
            Nested dict mapping country -> segment -> raw JSON text.

        Raises:
            MarsError: Failed request to the MARS API.
        """
        tasks: list[tuple[str, SegmentType, Task[str | None]]] = []
        try:
            async with asyncio.TaskGroup() as task_group:
                for country, segment, form_factor, idx_id in segments:
                    task: Task[str | None] = task_group.create_task(
                        self.get_suggestion_data(country, form_factor, idx_id)
                    )
                    tasks.append((country, segment, task))
        except ExceptionGroup as error_group:
            raise MarsError(error_group.exceptions)

        suggestions: defaultdict[str, dict[SegmentType, str]] = defaultdict(dict)

        for country, segment, task in tasks:
            result = task.result()
            if result is not None:
                suggestions[country][segment] = result

        return suggestions

    async def get_suggestion_data(
        self,
        country: str,
        form_factor: str,
        idx_id: str,
    ) -> str | None:
        """Fetch suggestions for a single country/form_factor segment.

        The MARS API returns ``{"suggestions": [...]}``. This method extracts
        the inner array and returns it as a JSON string suitable for
        ``AmpIndexManager.build()``.

        Adds ETag-based conditional fetching
        (HTTP ``If-None-Match`` / ``304 Not Modified``).

        Args:
            country: The country code.
            form_factor: The form factor string.
            idx_id: The index identifier for ETag tracking.

        Returns:
            A JSON array string of suggestions, or None if not modified (304).

        Raises:
            MarsError: Failed request to the MARS API.
        """
        tags = {"country": country, "form_factor": form_factor}
        headers: dict[str, str] = {}
        if idx_id in self.etags:
            headers["If-None-Match"] = self.etags[idx_id]

        url = urljoin(self.base_url, self.suggestion_url_path)
        try:
            params = {"_test_padding": "true"} if settings.mars.send_test_padding else {}
            response = await self.http_client.get(
                url,
                params={"country": country, "form_factor": form_factor, **params},
                headers=headers,
            )

            if response.status_code == 304:
                self.metrics_client.increment(
                    "mars.fetch", tags={**tags, "status": "not_modified"}
                )
                return None

            response.raise_for_status()

            self.metrics_client.gauge(
                "mars.fetch.response_size_bytes",
                value=len(response.content),
                tags=tags,
            )

            etag = response.headers.get("ETag")
            if etag:
                self.etags[idx_id] = etag

            # MARS wraps suggestions in {"suggestions": [...]}.
            # Extract the array for AmpIndexManager.build().
            try:
                data = response.json()
            except ValueError as exc:
                raise MarsError(f"Invalid JSON in response for {country}/{form_factor}") from exc

            if "suggestions" not in data:
                raise MarsError(
                    f"MARS response missing 'suggestions' key for {country}/{form_factor}"
                )

            suggestions_list = data["suggestions"]
            if not suggestions_list:
                logger.warning(
                    f"MARS returned empty suggestions for {country}/{form_factor}",
                )
                self.metrics_client.increment(
                    "mars.fetch", tags={**tags, "status": "empty_response"}
                )
                return None

            self.metrics_client.increment("mars.fetch", tags={**tags, "status": "success"})
            self.last_new_data_at = time.time()
            return json.dumps(suggestions_list)
        except httpx.HTTPError as error:
            self.metrics_client.increment("mars.fetch", tags={**tags, "status": "error"})
            raise MarsError(f"Failed to fetch suggestions for {country}/{form_factor}") from error
