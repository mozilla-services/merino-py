# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Framed Widgets backend."""

import asyncio
import pytest
import logging

from google.cloud.storage import Client
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from merino.providers.widgets.iframed.backends.framed import FramedWidgetsBackend
from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetGCS,
    FramedWidgetResponse,
)


WIDGET_MANIFEST = [
    FramedWidgetGCS(
        bucket_name="test bucket 1",
        cdn_host="https://test-bucket-1",
        enabled=True,
        id="test1",
        vendor="mozilla",
    ),
    FramedWidgetGCS(
        bucket_name="test bucket 2",
        cdn_host="https://test-bucket-2",
        enabled=True,
        id="test2",
        vendor="mozilla",
    ),
]


@pytest.fixture(name="gcs_client_mock")
def fixture_gcs_client_mock() -> Client:
    """Return a mock GCS Client."""
    return MagicMock(spec=Client)


@pytest.fixture(name="backend")
def fixture_backend(
    gcs_client_mock: Client,
    statsd_mock,
) -> FramedWidgetsBackend:
    """Return a FramedBackend instance for testing."""
    return FramedWidgetsBackend(gcs_client=gcs_client_mock, metrics_client=statsd_mock)


def make_widget(id: str, version: str) -> FramedWidgetResponse:
    """Build a FramedWidgetResponse for the given widget id and version."""
    return FramedWidgetResponse(
        enabled=True,
        id=id,
        vendor="mozilla",
        url=HttpUrl(f"https://cdn.example.com/{id}/{version}/index.html"),
    )


class TestFetch:
    """Test the entry point fetch function."""

    @pytest.mark.asyncio
    async def test_returns_widgets(self, backend: FramedWidgetsBackend) -> None:
        """Test the happy path."""
        backend.widgets_manifest = WIDGET_MANIFEST

        with patch.object(
            backend, "_build_widget_response", new=AsyncMock()
        ) as mock_build_response:
            mock_build_response.return_value = FramedWidgetResponse(
                enabled=True, id="test", vendor="mozilla", url=HttpUrl("https://mozilla.org")
            )

            result = await backend.fetch()

            # we should have a FramedWidgetResponse for each widget in the manifest
            assert len(result) == len(WIDGET_MANIFEST)

            for res in result:
                assert isinstance(res, FramedWidgetResponse)

    @pytest.mark.asyncio
    async def test_skips_widgets_when_gcs_lookup_fails(
        self, backend: FramedWidgetsBackend
    ) -> None:
        """Test fetch."""
        backend.widgets_manifest = WIDGET_MANIFEST

        with patch.object(
            backend, "_build_widget_response", new=AsyncMock()
        ) as mock_build_response:
            mock_build_response.side_effect = [
                FramedWidgetResponse(
                    enabled=True, id="test", vendor="mozilla", url=HttpUrl("https://mozilla.org")
                ),
                None,
            ]

            result = await backend.fetch()

            # we should have a FramedWidgetResponse for each widget in the manifest that doesn't error
            assert len(result) == len(WIDGET_MANIFEST) - 1

            for res in result:
                assert isinstance(res, FramedWidgetResponse)

    @pytest.mark.asyncio
    async def test_falls_back_to_cached_widget_when_lookup_fails(
        self, backend: FramedWidgetsBackend, statsd_mock, caplog: LogCaptureFixture
    ) -> None:
        """A failed lookup should return the previously fetched version of that widget."""
        backend.widgets_manifest = WIDGET_MANIFEST

        cached_widgets = {
            "test1": make_widget("test1", "1.0.0"),
            "test2": make_widget("test2", "1.0.0"),
        }
        fresh_widgets = {"test1": make_widget("test1", "2.0.0"), "test2": None}

        with patch.object(backend, "_build_widget_response", new=AsyncMock()) as mock_build:
            # first fetch succeeds for every widget and populates the cache
            mock_build.side_effect = lambda widget: cached_widgets[widget.id]

            assert await backend.fetch() == [cached_widgets["test1"], cached_widgets["test2"]]

            # second fetch: widget with id test1 has a new release, test2's lookup fails
            mock_build.side_effect = lambda widget: fresh_widgets[widget.id]

            caplog.set_level(logging.WARNING)

            result = await backend.fetch()

        # widget id test1 is fresh, test2 falls back to the cached 1.0.0, manifest order is kept
        assert result == [fresh_widgets["test1"], cached_widgets["test2"]]
        assert backend.cached_widgets["test1"] == fresh_widgets["test1"]

        # the fallback is logged and counted
        stale_logs = [r for r in caplog.records if "cached version" in r.message]

        assert len(stale_logs) == 1
        assert stale_logs[0].__dict__["id"] == "test2"

        statsd_mock.increment.assert_called_once_with(
            "providers.widgets.framed.stale", tags={"widget": "test2"}
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_cached_widget_when_task_is_cancelled(
        self, backend: FramedWidgetsBackend, statsd_mock
    ) -> None:
        """A cancelled (timed out) task should return the cached version of the widget."""
        backend.widgets_manifest = WIDGET_MANIFEST

        cached = make_widget("test2", "1.0.0")

        backend.cached_widgets["test2"] = cached

        async def build(widget: FramedWidgetGCS) -> FramedWidgetResponse:
            if widget.id == "test2":
                # simulate the task being cancelled by the task runner's timeout
                raise asyncio.CancelledError

            return make_widget(widget.id, "2.0.0")

        # patch the _build_widget_response function to force a timeout for widget id test2
        with patch.object(backend, "_build_widget_response", new=build):
            result = await backend.fetch()

        assert result == [make_widget("test1", "2.0.0"), cached]

        statsd_mock.increment.assert_called_once_with(
            "providers.widgets.framed.stale", tags={"widget": "test2"}
        )


class TestBuildWidgetResponse:
    """Test the _build_widget_response function."""

    @pytest.mark.asyncio
    async def test_returns_expected_response(self, backend: FramedWidgetsBackend):
        """Verify a FramedWidgetResponse is returned."""
        widget = WIDGET_MANIFEST[0]
        mocked_url = HttpUrl("https://mozilla.org")

        expected = FramedWidgetResponse(
            enabled=widget.enabled, id=widget.id, vendor=widget.vendor, url=mocked_url
        )

        with (
            patch.object(
                backend, "_get_latest_semver_from_gcs", new=AsyncMock()
            ) as mock_get_semver,
            patch.object(FramedWidgetsBackend, "build_public_url") as mock_build_url,
        ):
            mock_get_semver.return_value = "1.0.test"
            mock_build_url.return_value = mocked_url

            result = await backend._build_widget_response(widget)

            assert isinstance(result, FramedWidgetResponse)

            mock_build_url.assert_called_once()

            assert result == expected

    @pytest.mark.asyncio
    async def test_returns_none_when_fails_to_get_semver(
        self, backend: FramedWidgetsBackend, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Verify None is returned when the call to get the latest semver raises"""
        caplog.set_level(logging.WARNING)

        with (
            patch.object(
                backend, "_get_latest_semver_from_gcs", new=AsyncMock()
            ) as mock_get_release,
            patch.object(FramedWidgetsBackend, "build_public_url") as mock_build_url,
        ):
            mock_get_release.side_effect = Exception("GCS call raised")

            result = await backend._build_widget_response(WIDGET_MANIFEST[0])

            assert result is None

            mock_build_url.assert_not_called()

            # get error records
            error_records = filter_caplog(
                caplog.records,
                "merino.providers.widgets.iframed.backends.framed",
            )

            # verify expected error was logged
            assert len(error_records) == 1
            assert "Error retrieving latest semver for framed widget" == error_records[0].message

    @pytest.mark.asyncio
    async def test_returns_none_when_building_url_raises(
        self, backend: FramedWidgetsBackend, caplog: LogCaptureFixture, filter_caplog: Any
    ):
        """Verify None is returned when the call to get the latest semver raises"""
        caplog.set_level(logging.WARNING)

        with (
            patch.object(
                backend, "_get_latest_semver_from_gcs", new=AsyncMock()
            ) as mock_get_release,
            patch.object(FramedWidgetsBackend, "build_public_url") as mock_build_url,
        ):
            mock_get_release.return_value = "1.0.test"
            mock_build_url.side_effect = ValueError("error!")

            result = await backend._build_widget_response(WIDGET_MANIFEST[0])

            assert result is None

            mock_get_release.assert_awaited_once()
            mock_build_url.assert_called_once()

            # get error records
            error_records = filter_caplog(
                caplog.records,
                "merino.providers.widgets.iframed.backends.framed",
            )

            # verify expected error was logged
            assert len(error_records) == 1
            assert "Error retrieving latest semver for framed widget" == error_records[0].message


class TestGetLatestSemverFromGcs:
    """Test the _get_latest_semver_from_gcs function."""

    @pytest.mark.asyncio
    async def test_returns_highest_semver(self, backend: FramedWidgetsBackend) -> None:
        """Test the happy path."""
        with (
            patch.object(backend, "_get_bucket_folders", new=MagicMock()) as mock_get_folders,
            patch.object(FramedWidgetsBackend, "get_highest_semver") as mock_get_highest_semver,
        ):
            mock_get_highest_semver.return_value = "1.6.2"

            result = await backend._get_latest_semver_from_gcs("bucket-name-doesnt-matter")

            assert result == "1.6.2"
            mock_get_folders.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_no_semver_found(self, backend: FramedWidgetsBackend) -> None:
        """Test the function raises when no semver was found."""
        with (
            patch.object(backend, "_get_bucket_folders", new=MagicMock()) as mock_get_folders,
            patch.object(FramedWidgetsBackend, "get_highest_semver") as mock_get_highest_semver,
        ):
            mock_get_highest_semver.return_value = None

            with pytest.raises(ValueError):
                await backend._get_latest_semver_from_gcs("bucket-name-doesnt-matter")

            mock_get_folders.assert_called_once()


class TestBuildPublicUrl:
    """Test the static build_public_url helper."""

    def test_build_url(self, backend: FramedWidgetsBackend):
        """Verify the URL is built as expected."""
        result = backend.build_public_url(
            cdn_host="stage-widgets-test.merino.nonprod.webservices.mozgcp.net", semver="1.0.test"
        )

        assert result == HttpUrl(
            "https://stage-widgets-test.merino.nonprod.webservices.mozgcp.net/1.0.test/index.html"
        )


class TestGetHighestSemver:
    """Test the static filter_and_sort_semvers function."""

    def test_happy_path(self, backend: FramedWidgetsBackend) -> None:
        """Test that strings are filtered and sorted as expected."""
        valid_releases = {"1.6.2/", "1.0.20261030214548/", "1.4.0/", "1.3.20261112182920/"}

        random_folders = {"tmp/", "bak/", "7thelastthingirememberwas/", "1.0.1.0.1.0/"}

        assert backend.get_highest_semver(valid_releases.union(random_folders)) == "1.6.2"

    def test_no_valid_semvers(self, backend: FramedWidgetsBackend) -> None:
        """Test that no valid semver strings results in a None response."""
        random_folders = {"tmp/", "bak/", "7thelastthingirememberwas/", "1.0.1.0.1.0/"}

        assert backend.get_highest_semver(random_folders) is None

    def test_filters_out_prereleases_and_builds(self, backend: FramedWidgetsBackend) -> None:
        """Test that pre-release and build versions are skipped."""
        valid_releases = {
            "1.6.2/",
            "1.0.20261030214548/",
            "3.4.5-pre.2+build.4/",
            "2.4.5+build.5/",
            "2.3.5-0.1.2/",
            "1.3.20261112182920/",
        }

        assert backend.get_highest_semver(valid_releases) == "1.6.2"

    def test_only_prereleases_and_builds(self, backend: FramedWidgetsBackend) -> None:
        """Test that None is returned when only pre-release and build versions were found."""
        valid_releases = {"3.4.5-pre.2+build.4/", "2.4.5+build.5/", "2.3.5-0.1.2/"}

        assert backend.get_highest_semver(valid_releases) is None
