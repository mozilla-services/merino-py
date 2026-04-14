# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the logos provider module."""

import logging
from unittest.mock import MagicMock

import pytest
from pydantic import HttpUrl

from merino.providers.suggest.logos.provider import LogoCategory, Provider, STORAGE_BASE_URL
from tests.types import FilterCaplogFixture


@pytest.mark.parametrize(
    "category,key",
    [
        (LogoCategory.Airline, "aa"),
        (LogoCategory.Airline, "AA"),
    ],
    ids=["lowercase", "capitalized"],
)
def test_get_logo_url_exists(logos_provider: Provider, category: LogoCategory, key: str) -> None:
    """Returns the URL from the manifest when the entry exists (regardless of capitalization)."""
    result = logos_provider.get_logo_url(category, key)

    assert result == HttpUrl(f"{STORAGE_BASE_URL}/logos/airline/airline_aa.png")


def test_get_logo_url_not_found(
    logos_provider: Provider,
    caplog: pytest.LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    statsd_mock,
) -> None:
    """Returns None when the manifest has no entry for the given category and key."""
    with caplog.at_level(logging.WARNING):
        result = logos_provider.get_logo_url(LogoCategory.MLB, "zzz")

    assert result is None
    records = filter_caplog(caplog.records, "merino.providers.suggest.logos.provider")
    assert len(records) == 1
    assert "mlb" in records[0].message
    assert "zzz" in records[0].message

    # Increments miss metric
    statsd_mock.increment.assert_called_once_with(
        "manifest.lookup.miss",
        tags={"provider": "logos"},
    )


def test_get_logo_url_manifest_unavailable(
    logos_provider: Provider,
    logo_manifest_mock: MagicMock,
) -> None:
    """Returns None when the manifest data is not yet available."""
    logo_manifest_mock.data = None

    result = logos_provider.get_logo_url(LogoCategory.Airline, "aa")

    assert result is None
