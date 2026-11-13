# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Framed Widgets backend."""

import asyncio
import pytest

from pydantic import HttpUrl

from google.cloud.storage import Bucket, Client
from unittest.mock import MagicMock
from typing import Generator

from merino.providers.widgets.iframed.backends.framed import FramedWidgetsBackend
from merino.providers.widgets.iframed.backends.protocol import (
    FramedWidgetGCS,
    FramedWidgetResponse,
)


BUCKET_NAME = "framed-widget"
RELEASES = ["1.0.20261030214548", "1.3.20261112182920", "1.4.0"]
FOLDERS_TO_IGNORE = ["bak", "tmp"]
FILES_TO_IGNORE = [
    ("index.html", "text/html"),
    ("stuff.csv", "text/csv"),
    ("poof.png", "image/png"),
]


@pytest.fixture(name="framed_bucket")
def fixture_framed_bucket(gcs_storage_client: Client) -> Generator[Bucket, None, None]:
    """Create a bucket with a few semver release folders, as well as some files that should be ignored."""
    bucket = gcs_storage_client.create_bucket(BUCKET_NAME)

    # actual release folders - following semver naming converntion
    for release in RELEASES:
        bucket.blob(f"{release}/index.html").upload_from_string(
            "<html></html>", content_type="text/html"
        )

    # folders that should be ignored - do not follow semver naming convention
    for folder in FOLDERS_TO_IGNORE:
        bucket.blob(f"{folder}/index.html").upload_from_string(
            "<html></html>", content_type="text/html"
        )

    # files that should be ignored - live at the root, not in a folder
    for file, type in FILES_TO_IGNORE:
        bucket.blob(f"{file}").upload_from_string("...", content_type=type)

    yield bucket

    bucket.delete(force=True)


@pytest.fixture(name="backend")
def fixture_backend(gcs_storage_client: Client, framed_bucket: Bucket) -> FramedWidgetsBackend:
    """Return a backend wired to the fake GCS server."""
    backend = FramedWidgetsBackend(gcs_client=gcs_storage_client, metrics_client=MagicMock())
    backend.widgets_manifest = [
        FramedWidgetGCS(
            bucket_name=BUCKET_NAME,
            cdn_host="framed.example.com",
            enabled=True,
            id="test",
            vendor="mozilla",
        )
    ]

    return backend


class TestFetch:
    """Test fetch against the fake GCS server."""

    @pytest.mark.asyncio
    async def test_returns_latest_release_url(self, backend: FramedWidgetsBackend) -> None:
        """Returns latest semver/url from the bucket."""
        result = await backend.fetch()

        assert result == [
            FramedWidgetResponse(
                enabled=True,
                id="test",
                vendor="mozilla",
                url=HttpUrl("https://framed.example.com/1.4.0/index.html"),
            )
        ]

    @pytest.mark.asyncio
    async def test_picks_up_new_release_on_next_fetch(
        self, backend: FramedWidgetsBackend, framed_bucket: Bucket
    ) -> None:
        """Returns new release added between fetches."""
        first = await backend.fetch()

        assert str(first[0].url) == "https://framed.example.com/1.4.0/index.html"

        # 1.10.0 sorts below 1.4.0 alphabetically, so this also checks semver ordering
        framed_bucket.blob("1.10.0/index.html").upload_from_string(
            "<html></html>", content_type="text/html"
        )

        second = await backend.fetch()

        assert str(second[0].url) == "https://framed.example.com/1.10.0/index.html"

    @pytest.mark.asyncio
    async def test_ignores_prerelease_folders(
        self, backend: FramedWidgetsBackend, framed_bucket: Bucket
    ) -> None:
        """Does not return a pre-release folder."""
        framed_bucket.blob("2.0.0-beta.1/index.html").upload_from_string(
            "<html></html>", content_type="text/html"
        )

        result = await backend.fetch()

        assert str(result[0].url) == "https://framed.example.com/1.4.0/index.html"

    @pytest.mark.asyncio
    async def test_falls_back_to_cache_when_bucket_lookup_fails(
        self, backend: FramedWidgetsBackend
    ) -> None:
        """Returns cached value when lookup against fake GCS fails."""
        first = await backend.fetch()

        # point the widget at a bucket that doesn't exist, so GCS returns a 404
        backend.widgets_manifest[0].bucket_name = "does-not-exist"

        second = await backend.fetch()

        assert second == first

    @pytest.mark.asyncio
    async def test_skips_widget_with_missing_bucket_on_cold_start(
        self, backend: FramedWidgetsBackend
    ) -> None:
        """Omits a widget with a bucket that doesn't exist."""
        backend.widgets_manifest.append(
            FramedWidgetGCS(
                bucket_name="does-not-exist",
                cdn_host="missing.example.com",
                enabled=True,
                id="missing",
                vendor="mozilla",
            )
        )

        result = await backend.fetch()

        assert len(result) == len(backend.widgets_manifest) - 1

        # assert the id returned matches the id set in the mocked backend fixture
        assert [w.id for w in result] == ["test"]


class TestGetBucketFolders:
    """Tests against the _get_bucket_folders function."""

    @pytest.mark.asyncio
    async def test_returns_all_folders_in_gcs_bucket(self, backend: FramedWidgetsBackend) -> None:
        """Verify the function returns all folders in the bucket."""
        # combined list to test against
        # (filtering by semver naming convention happens elsewhere)
        expected_folders = RELEASES + FOLDERS_TO_IGNORE

        # get the folders from the GCS bucket
        folders = await asyncio.to_thread(backend._get_bucket_folders, bucket_name=BUCKET_NAME)

        # make sure we have the right number of folders
        assert len(folders) == len(expected_folders)

        # make sure each expected folder was found
        for folder in folders:
            assert folder.strip("/") in expected_folders
