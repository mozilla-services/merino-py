# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the widget API endpoint tests."""

from datetime import timedelta
from typing import Any

import pytest

from merino.cache.none import NoCacheAdapter
from merino.main import app
from merino.providers.widgets import get_iframed_widgets_provider, get_wrexham_provider
from merino.providers.widgets.iframed.provider import Provider as IframedWidgetsProvider
from merino.providers.widgets.wrexham.provider import WrexhamProvider
from merino.providers.widgets.wrexham.store import WrexhamStore


class InMemoryCache(NoCacheAdapter):
    """In-memory stand-in for a cache adapter."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        """Return the stored value, or None."""
        return self.values.get(key)

    async def set(
        self, key: str, value: bytes | str, ttl: timedelta | None = None, nx: bool = False
    ) -> None:
        """Store a value."""
        self.values[key] = value.encode() if isinstance(value, str) else value


@pytest.fixture(name="store")
def fixture_store() -> WrexhamStore:
    """Create a store backed by an in-memory cache."""
    return WrexhamStore(
        cache=InMemoryCache(),
        fixtures_ttl=timedelta(hours=1),
        live_matches_ttl=timedelta(minutes=5),
        standings_ttl=timedelta(hours=1),
    )


@pytest.fixture(name="wrexham_provider")
def fixture_wrexham_provider(store: WrexhamStore, statsd_mock: Any) -> WrexhamProvider:
    """Create a Wrexham provider that serves mock data."""
    return WrexhamProvider(store=store, metrics_client=statsd_mock, mock_data_enabled=True)


@pytest.fixture(name="inject_wrexham_provider", autouse=True)
def fixture_inject_wrexham_provider(wrexham_provider: WrexhamProvider):
    """Inject the Wrexham provider into the app for testing."""

    def get_test_wrexham_provider() -> WrexhamProvider:
        return wrexham_provider

    app.dependency_overrides[get_wrexham_provider] = get_test_wrexham_provider
    yield
    del app.dependency_overrides[get_wrexham_provider]


@pytest.fixture(name="iframed_widgets_provider")
def fixture_iframed_widgets_provider(statsd_mock: Any) -> IframedWidgetsProvider:
    """Create an iframed widgets provider."""
    return IframedWidgetsProvider(
        metrics_client=statsd_mock,
        name="test_iframed_widgets",
        enabled=True,
    )


@pytest.fixture(name="inject_iframed_widgets_provider", autouse=True)
def fixture_inject_iframed_widgets_provider(iframed_widgets_provider: IframedWidgetsProvider):
    """Inject the iframed widgets provider into the app for testing."""

    def get_test_iframed_widgets_provider() -> IframedWidgetsProvider:
        return iframed_widgets_provider

    app.dependency_overrides[get_iframed_widgets_provider] = get_test_iframed_widgets_provider
    yield
    del app.dependency_overrides[get_iframed_widgets_provider]
