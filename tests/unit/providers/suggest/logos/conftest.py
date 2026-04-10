# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the logos provider unit tests."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import HttpUrl

from merino.providers.suggest.logos.provider import (
    Logo,
    LogoCategory,
    LogoEntry,
    LogoManifest,
    Provider,
    STORAGE_BASE_URL,
)
from merino.utils.synced_gcs_blob_v2 import SyncedGcsBlobV2


def make_logo_entry(category: LogoCategory, key: str) -> LogoEntry:
    """Create a LogoEntry using the standard URL naming convention."""
    url = HttpUrl(f"{STORAGE_BASE_URL}/logos/{category}/{category}_{key.lower()}.png")
    return LogoEntry(
        name=key.upper(),
        abbreviation=key.upper(),
        logo=Logo(url=url, format="png"),
    )


def make_manifest(*entries: tuple[LogoCategory, str]) -> LogoManifest:
    """Build a LogoManifest with the given (category, key) pairs."""
    lookups: dict[LogoCategory, dict[str, LogoEntry]] = {}
    for category, key in entries:
        lookups.setdefault(category, {})[key.upper()] = make_logo_entry(category, key)
    return LogoManifest(
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        lookups=lookups,
    )


@pytest.fixture
def logo_manifest_mock() -> MagicMock:
    """Return a mocked SyncedGcsBlobV2[LogoManifest] with a default manifest."""
    mock = MagicMock(spec=SyncedGcsBlobV2)
    mock.data = make_manifest(
        (LogoCategory.Airline, "aa"),
    )
    return mock


@pytest.fixture(name="logos_provider")
def fixture_logos_provider(statsd_mock, logo_manifest_mock) -> Provider:
    """Return a Provider instance with a mocked logo manifest."""
    return Provider(metrics_client=statsd_mock, logo_manifest=logo_manifest_mock)
