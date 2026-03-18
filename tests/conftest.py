# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the tests directory."""

from logging import LogRecord
from typing import Any

import aiodogstatsd
import pytest
from pytest_mock import MockerFixture

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


@pytest.fixture(name="statsd_mock")
def fixture_statsd_mock(mocker: MockerFixture) -> Any:
    """Create a StatsD client mock object for testing."""
    return mocker.MagicMock(spec=aiodogstatsd.Client)
