"""The adMarketplace (AMP) search term sanitization exempt, backed by the MARS API.

AMP keywords are advertiser-supplied and already public, so a search term matching one
carries no PII risk and can skip sanitization entirely.
"""

import asyncio
import contextlib
import logging
import time
from urllib.parse import urljoin

import httpx
from merino_common.utils import cron
from opentelemetry import metrics

logger = logging.getLogger(__name__)

_meter = metrics.get_meter("fleece")
_fetch_counter = _meter.create_counter(
    name="sanitize.exempts.amp.fetch",
    unit="{request}",
    description="Number of MARS fetches for AMP keywords, labeled by segment and outcome.",
)
_keywords_gauge = _meter.create_gauge(
    name="sanitize.exempts.amp.keywords",
    unit="{keyword}",
    description="Number of distinct AMP keywords currently exempt from sanitization.",
)

# The outcome of fetching one segment: `(keywords, errored)`.
#
# `keywords` is None whenever the segment yielded no new data -- a 304, an empty payload,
# or a failure -- in which case the segment's previously stored keywords are kept.
# `errored` separates a failure from the other two, since only a failure should hold back
# `last_fetch_at` and so trigger an early retry.
SegmentResult = tuple[set[str] | None, bool]


class AmpExempt:
    """Exempt search terms that match an AMP keyword served by MARS.

    Keywords are fetched per `country/form_factor` segment at initialization and refreshed
    by a cron job thereafter, using ETags so an unchanged segment costs a 304.

    Args:
        base_url: The base URL for the MARS API.
        suggestion_url_path: The URL path for fetching suggestions.
        countries: Country codes to fetch keywords for.
        form_factors: Form factors to fetch keywords for.
        connect_timeout_sec: Timeout in seconds for establishing a connection.
        request_timeout_sec: Timeout in seconds for a request.
        resync_interval_sec: Time between re-syncs of keyword data.
        cron_interval_sec: Interval between cron ticks. Should be shorter than
            `resync_interval_sec` so a failed re-sync is retried soon.
    """

    def __init__(
        self,
        base_url: str,
        suggestion_url_path: str,
        countries: list[str],
        form_factors: list[str],
        connect_timeout_sec: float,
        request_timeout_sec: float,
        resync_interval_sec: float,
        cron_interval_sec: float,
    ) -> None:
        self.base_url = base_url
        self.suggestion_url_path = suggestion_url_path
        # Deduplicate config lists (defensive against dynaconf_merge).
        self.countries = list(dict.fromkeys(countries))
        self.form_factors = list(dict.fromkeys(form_factors))
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout_sec, connect=connect_timeout_sec),
        )
        # Keywords are held per segment rather than as one flat set because a refresh can
        # return fresh data for one segment and a 304 for another. Rebuilding the flat set
        # from only the fresh responses would drop every 304'd segment's keywords.
        self.segment_keywords: dict[str, set[str]] = {}
        # The flat union of `segment_keywords`, which is what `is_exempt` reads.
        self.keywords: frozenset[str] = frozenset()
        # ETag tracking per segment for conditional fetching.
        self.etags: dict[str, str] = {}
        self.last_fetch_at: float = 0.0
        self.cron_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Fetch keywords, then start the cron job that keeps them fresh.

        A failed initial fetch is not fatal: `is_exempt` reports False for everything
        until the cron job manages a fetch, so terms are sanitized as non-exempt.
        """
        try:
            await self._fetch()
        except Exception as e:
            logger.warning(
                "Failed to fetch AMP keywords from MARS, will retry it soon",
                extra={"error message": f"{e}"},
            )
            # Set the last fetch timestamp to 0 so that the cron job will retry
            # the fetch upon the next tick.
            self.last_fetch_at = 0

        cron_job = cron.Job(
            name="resync_amp_exempt_keywords",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch,
        )
        # Store the created task on the instance variable. Otherwise it will get
        # garbage collected because asyncio's runtime only holds a weak reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    async def shutdown(self) -> None:
        """Stop the cron job and close the HTTP client."""
        if self.cron_task is not None:
            self.cron_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.cron_task
            self.cron_task = None
        await self.http_client.aclose()

    def is_exempt(self, search_term: str) -> bool:
        """Return whether the search term matches an AMP keyword.

        MARS keywords are lowercase, so the term is normalized the same way merino's adm
        provider normalizes queries before looking them up.
        """
        return search_term.strip().lower() in self.keywords

    def _should_fetch(self) -> bool:
        """Check if it should fetch keyword data from MARS."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    async def _fetch(self) -> None:
        """Refresh keywords for every segment concurrently and rebuild the flat set.

        `_fetch_segment` never raises, so one unhealthy segment cannot abort the task
        group and discard its siblings' results.
        """
        tasks: list[tuple[str, asyncio.Task[SegmentResult]]] = []
        async with asyncio.TaskGroup() as task_group:
            for country in self.countries:
                for form_factor in self.form_factors:
                    tasks.append(
                        (
                            f"{country}/{form_factor}",
                            task_group.create_task(self._fetch_segment(country, form_factor)),
                        )
                    )

        errored = False
        for segment, task in tasks:
            keywords, segment_errored = task.result()
            errored = errored or segment_errored
            if keywords is not None:
                self.segment_keywords[segment] = keywords

        # Swapped in with a single assignment, so readers never observe a partial set.
        self.keywords = frozenset().union(*self.segment_keywords.values())
        _keywords_gauge.set(len(self.keywords))

        # Leave `last_fetch_at` alone when a segment failed, so the cron job retries on
        # its next tick instead of waiting out the full resync interval. The retry is
        # cheap: the healthy segments answer 304.
        if not errored:
            self.last_fetch_at = time.time()

    async def _fetch_segment(self, country: str, form_factor: str) -> SegmentResult:
        """Fetch the AMP keywords of a single `country/form_factor` segment.

        Every failure mode is handled here rather than raised, so the caller can apply a
        partial refresh. The ETag is only stored once a response has been parsed in full,
        so a segment can never be pinned to data that was never used.
        """
        segment = f"{country}/{form_factor}"
        tags = {"country": country, "form_factor": form_factor}
        headers: dict[str, str] = {}
        if segment in self.etags:
            headers["If-None-Match"] = self.etags[segment]

        url = urljoin(self.base_url, self.suggestion_url_path)
        try:
            response = await self.http_client.get(
                url,
                params={"country": country, "form_factor": form_factor},
                headers=headers,
            )

            if response.status_code == 304:
                _fetch_counter.add(1, {**tags, "status": "not_modified"})
                return None, False

            response.raise_for_status()

            suggestions = response.json()["suggestions"]
            if not suggestions:
                logger.warning(f"MARS returned empty suggestions for {segment}")
                _fetch_counter.add(1, {**tags, "status": "empty_response"})
                return None, False

            keywords = {
                normalized
                for suggestion in suggestions
                for keyword in suggestion.get("keywords") or ()
                if (normalized := keyword.strip().lower())
            }
        except httpx.HTTPError as error:
            logger.warning(
                f"Failed to fetch AMP keywords for {segment}",
                extra={"error message": f"{error}"},
            )
            _fetch_counter.add(1, {**tags, "status": "error"})
            return None, True
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            # The payload was not JSON, was missing `suggestions`, or had an unexpected shape.
            logger.warning(
                f"Malformed MARS response for {segment}",
                extra={"error message": f"{error}"},
            )
            _fetch_counter.add(1, {**tags, "status": "error"})
            return None, True

        if etag := response.headers.get("ETag"):
            self.etags[segment] = etag
        _fetch_counter.add(1, {**tags, "status": "success"})
        return keywords, False
