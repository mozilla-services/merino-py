"""The CCR follower check: scrape `GET _ccr/stats` on a follower cluster."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch

from merino_hook_eye.ccr import metrics
from merino_hook_eye.ccr.scraper import CcrStatsScraper
from merino_hook_eye.checks import RunningCheck, run_check
from merino_hook_eye.configs import settings

NAME = "ccr_follower"


def build_client() -> AsyncElasticsearch:
    """Create the client for the follower cluster from settings."""
    config = settings.ccr_follower
    return AsyncElasticsearch(
        config.url,
        # An empty key would still send an `Authorization` header.
        api_key=config.api_key or None,
        request_timeout=float(config.request_timeout_sec),
    )


@asynccontextmanager
async def start() -> AsyncGenerator[RunningCheck]:
    """Scrape the follower on a cron until the context exits, then close the client."""
    client = build_client()
    scraper = CcrStatsScraper(client, index_patterns=list(settings.ccr_follower.index_patterns))
    try:
        async with run_check(
            name=NAME,
            interval_sec=float(settings.ccr_follower.interval_sec),
            run=scraper.scrape,
            seconds_since_last_attempt=scraper.seconds_since_last_attempt,
            on_stop=metrics.clear,
        ) as check:
            yield check
    finally:
        await client.close()
