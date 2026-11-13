# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the iframed widget provider module."""

import asyncio
import datetime
import freezegun
import pytest

from pydantic import HttpUrl
from pytest_mock import MockerFixture
from typing import Any
from unittest.mock import AsyncMock, patch

from merino.providers.widgets.iframed.provider import Provider as FramedWidgetProvider
from merino.providers.widgets.iframed.backends.framed import FramedWidgetsBackend
from merino.providers.widgets.iframed.backends.protocol import FramedWidgetResponse


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture):
    """Return a mock FramedWidgetsBackend."""
    return mocker.AsyncMock(spec=FramedWidgetsBackend)


@pytest.fixture(name="provider")
def fixture_provider(backend_mock: Any, statsd_mock: Any) -> FramedWidgetProvider:
    """Return a Provider instance for testing."""
    return FramedWidgetProvider(
        backend=backend_mock,
        cron_interval_sec=60,
        enabled=True,
        metrics_client=statsd_mock,
        name="iframed Widget Provider",
        resync_interval_sec=600,
    )


class TestInitialize:
    """Tests against the initialize method."""

    @pytest.mark.asyncio
    async def test_noop_with_cron_disabled(self, provider: FramedWidgetProvider) -> None:
        """Test that no cron processing happens if the cron is disabled."""
        provider._cron_enabled = False

        with patch.object(provider, "_fetch", new=AsyncMock()) as mock_fetch:
            await provider.initialize()

            mock_fetch.assert_not_awaited()
            assert provider.cron_task is None

    @pytest.mark.asyncio
    async def test_cron_created(self, provider: FramedWidgetProvider) -> None:
        """Test that the cron is created."""
        provider._cron_enabled = True

        with (
            patch("asyncio.create_task", wraps=asyncio.create_task) as mock_create_task,
            patch("merino.providers.widgets.iframed.provider.cron.Job") as mock_cron,
        ):
            mock_job_instance = AsyncMock(name="mock_cron_job")
            mock_cron.return_value = mock_job_instance

            await provider.initialize()

            mock_cron.assert_called_once_with(
                name="refresh_framed_widgets",
                interval=provider.cron_interval_sec,
                condition=provider._should_fetch,
                task=provider._fetch,
            )

            mock_create_task.assert_called_once()

            args, _ = mock_create_task.call_args

            assert asyncio.iscoroutine(args[0])

            assert provider.cron_task is not None

            provider.shutdown()

    @freezegun.freeze_time("2026-11-10 23:23:23", tz_offset=0)
    @pytest.mark.asyncio
    async def test_fetch_calls_backend_and_sets_last_fetch_at(
        self, provider: FramedWidgetProvider
    ) -> None:
        """Test that fetch calls the backend, gets results, and sets last_fetch_at."""
        provider._cron_enabled = True

        fake_widgets_response = [
            FramedWidgetResponse(
                enabled=True, id="travel", vendor="mozilla", url=HttpUrl("https://www.mozilla.org")
            )
        ]

        with patch.object(provider.backend, "fetch", new=AsyncMock()) as mock_fetch:
            mock_fetch.return_value = fake_widgets_response

            await provider.initialize()

            await provider._fetch()

            assert provider.widgets_response == fake_widgets_response

            assert (
                provider.last_fetch_at
                == datetime.datetime(
                    year=2026, month=11, day=10, hour=23, minute=23, second=23
                ).timestamp()
            )

        # make sure the cron is cancelled
        provider.shutdown()


class TestShutdown:
    """Test shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_with_cron_no_errors(self, provider: FramedWidgetProvider) -> None:
        """Test that shutdown executes after the cron has started."""
        provider._cron_enabled = True

        # make sure fetch doesn't actually do anything
        with patch.object(provider, "_fetch", new=AsyncMock()):
            await provider.initialize()

            assert provider.cron_task is not None

            provider.shutdown()

            assert provider.cron_task is None

    @pytest.mark.asyncio
    async def test_shutdown_without_cron_no_errors(self, provider: FramedWidgetProvider) -> None:
        """Test that shutdown executes when cron never started."""
        provider._cron_enabled = False

        # make sure fetch doesn't actually do anything
        with patch.object(provider, "_fetch", new=AsyncMock()):
            await provider.initialize()

            provider.shutdown()

            assert provider.cron_task is None


class TestGetWidgets:
    """Tests against get_widgets"""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_provider_disabled(
        self, provider: FramedWidgetProvider
    ) -> None:
        """Test that no widgets are returned when the provider is disabled."""
        provider._enabled = False

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 0

    @pytest.mark.asyncio
    async def test_returns_hard_coded_widgets_list(self, provider: FramedWidgetProvider) -> None:
        """Test that get_widgets returns the hard-coded list."""
        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

    @pytest.mark.asyncio
    async def test_returns_stage_widgets_for_stage_env(
        self, provider: FramedWidgetProvider, force_env
    ) -> None:
        """Test that get_widgets returns the hard-coded staging list."""
        force_env("stage")

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

        for widget in response.widgets:
            assert ".nonprod.webservices.mozgcp.net" in str(widget.url.host)

    @pytest.mark.asyncio
    async def test_returns_prod_widgets_for_prod_env(
        self, provider: FramedWidgetProvider, force_env
    ) -> None:
        """Test that get_widgets returns the hard-coded production list."""
        force_env("production")

        response = await provider.get_widgets(locale="en-US")

        assert response.widgets is not None
        assert len(response.widgets) == 5

        for widget in response.widgets:
            assert ".prod.webservices.mozgcp.net" in str(widget.url.host)
