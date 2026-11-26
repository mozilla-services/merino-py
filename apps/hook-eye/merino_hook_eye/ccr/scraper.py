"""Scraper for `GET _ccr/stats` on the follower cluster."""

import logging
import time

from elasticsearch import AsyncElasticsearch
from pydantic import ValidationError

from merino_hook_eye.ccr import metrics
from merino_hook_eye.ccr.stats import parse_ccr_stats

logger = logging.getLogger(__name__)


class CcrStatsScraper:
    """Fetch `GET _ccr/stats` and publish the result as the current metrics snapshot."""

    def __init__(self, client: AsyncElasticsearch, *, index_patterns: list[str]) -> None:
        self._client = client
        self._index_patterns = index_patterns
        # Counts from creation, so the first scrape gets a full staleness window.
        self._last_attempt = time.monotonic()

    def seconds_since_last_attempt(self) -> float:
        """Return the seconds since the last scrape finished, successfully or not."""
        return time.monotonic() - self._last_attempt

    async def scrape(self) -> None:
        """Fetch and publish one snapshot.

        On any failure the previous snapshot is dropped, so stale values are never reported
        as current, and the error is re-raised for the cron job to log as a warning. A
        response that doesn't match the models is also logged as an error, which reaches
        Sentry: unlike a request failure, it needs a code change.
        """
        try:
            response = await self._client.ccr.stats()
            stats = parse_ccr_stats(dict(response.body), self._index_patterns)
        except Exception as error:
            metrics.clear()
            metrics.scrape_counter.add(1, {"status": "error"})
            if isinstance(error, ValidationError):
                logger.error("GET _ccr/stats returned an unexpected response", exc_info=error)
            raise
        finally:
            self._last_attempt = time.monotonic()

        metrics.publish(stats)
        metrics.scrape_counter.add(1, {"status": "success"})
        logger.debug(
            "Scraped CCR stats",
            extra={
                "shards": len(stats.shards),
                "remote_clusters": len(stats.auto_follow.auto_followed_clusters),
            },
        )
