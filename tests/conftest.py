# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the tests directory."""

from datetime import datetime, timezone
from logging import LogRecord
from typing import Any

import aiodogstatsd
import pytest
from pytest_mock import MockerFixture

from merino.utils.logos import Logo, LogoCategory, LogoManifest
from tests.types import FilterCaplogFixture


# When the conftest plugin is loaded the following fixtures will be loaded as well.
pytest_plugins = [
    "tests.integration.fixtures.gcs",
    "tests.integration.fixtures.metrics",
    "tests.integration.api.v1.curated_recommendations.corpus_backends.fixtures",
]


@pytest.fixture(scope="session", name="filter_caplog")
def fixture_filter_caplog() -> FilterCaplogFixture:
    """Return a function that will filter pytest captured log records for a given logger
    name.
    """

    def filter_caplog(records: list[LogRecord], logger_name: str) -> list[LogRecord]:
        """Filter pytest captured log records for a given logger name"""
        return [record for record in records if record.name == logger_name]

    return filter_caplog


@pytest.fixture(autouse=True)
def reset_storage_client() -> None:
    """Reset the shared GCS storage client singleton between tests.
    The Storage client holds an aiohttp session bound to an event loop.
    The integration tests specifically create a fresh event loop per test,
    which leaves the cached session in a broken state, unless reset.
    """
    import merino.utils.storage as storage_module

    storage_module._shared_storage_client = None


@pytest.fixture(name="statsd_mock")
def fixture_statsd_mock(mocker: MockerFixture) -> Any:
    """Create a StatsD client mock object for testing."""
    return mocker.MagicMock(spec=aiodogstatsd.Client)


@pytest.fixture
def make_manifest():
    """Return a factory for building LogoManifest instances in tests."""

    def _make(*entries: tuple[LogoCategory, str]) -> LogoManifest:
        lookups: dict[LogoCategory, dict[str, Logo]] = {}
        for category, key in entries:
            lookups.setdefault(category, {})[key.upper()] = Logo(
                name=key.upper(),
                url=f"logos/{category}/{category}_{key.lower()}.png",
            )
        return LogoManifest(
            generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            lookups=lookups,
        )

    return _make


@pytest.fixture(autouse=True)
def mock_load_manifest(request, mocker: MockerFixture, make_manifest) -> None:
    """Patch load_manifest for all tests to avoid reading the real file.

    Tests marked with @pytest.mark.restore_load_manifest bypass this mock
    and exercise the real file I/O.
    """
    if request.node.get_closest_marker("restore_load_manifest"):
        return
    mocker.patch(
        "merino.utils.logos.load_manifest",
        return_value=make_manifest((LogoCategory.Airline, "aa")),
    )
