# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the logos provider module."""

import logging
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from merino.providers.suggest.logos.provider import LogoCategory, STORAGE_BASE_URL
from merino.providers.suggest.logos.provider import Provider
from tests.types import FilterCaplogFixture


@pytest.mark.asyncio
async def test_get_logo_url_exists(logos_provider: Provider) -> None:
    """Returns a GCS URL when the blob exists."""
    result = await logos_provider.get_logo_url(LogoCategory.Airline, "aa")

    assert result == HttpUrl(f"{STORAGE_BASE_URL}/logos/airline/airline_aa.png")


@pytest.mark.asyncio
async def test_get_logo_url_not_found(
    logos_provider: Provider,
    fixture_logos_bucket: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Returns None and logs a warning when the blob does not exist."""
    fixture_logos_bucket.blob_exists.return_value = False

    with caplog.at_level(logging.WARNING):
        result = await logos_provider.get_logo_url(LogoCategory.MLB, "bos")

    assert result is None
    records = filter_caplog(caplog.records, "merino.providers.suggest.logos.provider")
    assert len(records) == 1
    assert "bos" in records[0].message
    assert "mlb" in records[0].message


@pytest.mark.asyncio
async def test_get_logo_url_increments_found_metric(logos_provider: Provider, statsd_mock) -> None:
    """Increments a found metric when the blob exists."""
    await logos_provider.get_logo_url(LogoCategory.NBA, "lal")

    statsd_mock.increment.assert_called_once_with(
        "gcs.blob.fetch",
        tags={"provider": "logos", "result": "found"},
    )


@pytest.mark.asyncio
async def test_get_logo_url_increments_not_found_metric(
    logos_provider: Provider, fixture_logos_bucket: AsyncMock, statsd_mock
) -> None:
    """Increments a not found metric when the blob does not exist."""
    fixture_logos_bucket.blob_exists.return_value = False

    await logos_provider.get_logo_url(LogoCategory.NFL, "ne")

    statsd_mock.increment.assert_called_once_with(
        "gcs.blob.fetch",
        tags={"provider": "logos", "result": "not_found"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,key",
    [
        (LogoCategory.Airline, "ua"),
        (LogoCategory.MLB, "nyy"),
        (LogoCategory.NBA, "lal"),
        (LogoCategory.NFL, "gb"),
        (LogoCategory.NHL, "tor"),
        (LogoCategory.NHL, "TOR"),
    ],
    ids=["airline", "mlb", "nba", "nfl", "nhl", "capitalized"],
)
async def test_get_logo_url_blob_name_format(
    logos_provider: Provider, category: LogoCategory, key: str
) -> None:
    """URL follows the /logos/{category}/{category}_{key}.png naming convention."""
    result = await logos_provider.get_logo_url(category, key)

    assert result == HttpUrl(f"{STORAGE_BASE_URL}/logos/{category}/{category}_{key.lower()}.png")
