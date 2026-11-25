"""Unit tests for merino_hook_eye.ccr.scraper."""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from elasticsearch import ConnectionError as EsConnectionError
from merino_common.testing.metrics import find_point
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from pydantic import ValidationError

from merino_hook_eye.ccr import metrics as ccr_metrics
from merino_hook_eye.ccr.scraper import CcrStatsScraper
from merino_hook_eye.ccr.stats import parse_ccr_stats

_PATTERNS = ["*wiki-*", "*sports-*"]


def _scrape_count(reader: InMemoryMetricReader, status: str) -> float:
    """Return the scrape counter's value for `status`."""
    point = find_point(reader, "merino.ccr.scrape", status=status)
    return point.value if point is not None else 0


def _client(**stats_kwargs: Any) -> MagicMock:
    """Build a stand-in AsyncElasticsearch whose `ccr.stats()` is an AsyncMock."""
    client = MagicMock()
    client.ccr.stats = AsyncMock(**stats_kwargs)
    return client


@pytest.mark.asyncio
async def test_scrape_publishes_snapshot(
    metric_reader: InMemoryMetricReader, ccr_stats_body: dict[str, Any]
) -> None:
    """A successful scrape publishes the parsed stats and counts a success."""
    client = _client(return_value=MagicMock(body=ccr_stats_body))
    before = _scrape_count(metric_reader, "success")

    await CcrStatsScraper(client, index_patterns=_PATTERNS).scrape()

    assert ccr_metrics.latest() == parse_ccr_stats(ccr_stats_body, _PATTERNS)
    assert _scrape_count(metric_reader, "success") == before + 1
    client.ccr.stats.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stats_kwargs",
    [
        {"side_effect": EsConnectionError("follower unreachable")},
        {"return_value": MagicMock(body={"follow_stats": {}})},
    ],
    ids=["request-error", "malformed-body"],
)
async def test_scrape_failure_clears_snapshot(
    metric_reader: InMemoryMetricReader,
    ccr_stats_body: dict[str, Any],
    stats_kwargs: dict[str, Any],
) -> None:
    """A failed scrape drops the last snapshot, counts an error, and re-raises."""
    ccr_metrics.publish(parse_ccr_stats(ccr_stats_body, _PATTERNS))
    before = _scrape_count(metric_reader, "error")

    with pytest.raises(Exception):
        await CcrStatsScraper(_client(**stats_kwargs), index_patterns=_PATTERNS).scrape()

    assert ccr_metrics.latest() is None
    assert _scrape_count(metric_reader, "error") == before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stats_kwargs", "logs_error"),
    [
        ({"side_effect": EsConnectionError("follower unreachable")}, False),
        ({"return_value": MagicMock(body={"follow_stats": {}})}, True),
    ],
    ids=["request-error", "malformed-body"],
)
async def test_only_unexpected_responses_log_an_error(
    caplog: pytest.LogCaptureFixture, stats_kwargs: dict[str, Any], logs_error: bool
) -> None:
    """A response the models reject is logged as an error, for Sentry; a request failure is
    left to the cron job's warning.
    """
    with pytest.raises(Exception):
        await CcrStatsScraper(_client(**stats_kwargs), index_patterns=_PATTERNS).scrape()

    errors = [
        record
        for record in caplog.records
        if record.name == "merino_hook_eye.ccr.scraper" and record.levelno == logging.ERROR
    ]
    if logs_error:
        [record] = errors
        assert record.exc_info is not None
        assert isinstance(record.exc_info[1], ValidationError)
    else:
        assert errors == []
