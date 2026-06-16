# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Picture of the Day Provider."""

import pytest
import freezegun

from typing import cast
from pydantic import HttpUrl
from unittest.mock import call, AsyncMock
from httpx import AsyncClient, HTTPError, Request, Response
from pytest_mock import MockerFixture
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPotdBackend,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock, mocker: MockerFixture, gcs_storage_client, gcs_storage_bucket
) -> WikimediaPotdBackend:
    """Return a WikimediaPotdBackend instance for testing."""
    return WikimediaPotdBackend(
        metrics_client=statsd_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        feed_url="https://example.com/feed",
        gcs_uploader=GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test-cdn-name",
        ),
    )


class TestUploadImageMethod:
    """Tests for the upload_image method."""

    @freezegun.freeze_time("2026-06-07")
    def test_thumbnail_upload_only_success(
        self, backend: WikimediaPotdBackend, gcs_storage_client, gcs_storage_bucket
    ) -> None:
        """Test upload_image method successfully uploads an image and returns a public cdn url."""
        test_image = Image(content=b"", content_type="Image/jpeg")

        # call the backend method to upload the image
        backend.upload_image(image=test_image, is_thumbnail=True)

        # get the blob (image) from the same bucket assigned to the gcs_uploader instance of the backend object
        blobs_in_bucket = list(gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs())

        # should be only one blob (thumbnail image)
        assert len(blobs_in_bucket) == 1
        assert blobs_in_bucket[0].name == "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"

    @freezegun.freeze_time("2026-06-07")
    def test_thumbnail_and_hi_res_success(
        self, backend: WikimediaPotdBackend, gcs_storage_client, gcs_storage_bucket
    ) -> None:
        """Test upload_image method successfully uploads two images and returns public cdn urls."""
        test_image = Image(content=b"", content_type="Image/jpeg")

        # call the backend method to upload the thumbnail and hi-res image
        backend.upload_image(image=test_image, is_thumbnail=True)
        backend.upload_image(image=test_image, is_thumbnail=False)

        # get the blob (image) from the same bucket assigned to the gcs_uploader instance of the backend object
        blobs_in_bucket = list(gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs())

        # should be two blobs (thumbnail and hi-res)
        assert len(blobs_in_bucket) == 2
        assert blobs_in_bucket[0].name == "rss/wikimedia_potd/POTD_2026-06-07_hi_res.jpeg"
        assert blobs_in_bucket[1].name == "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"

    def test_captures_sentry_exception(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Test upload_image method successfully uploads two images and returns public cdn urls."""
        test_image = Image(content=b"", content_type="Image/jpeg")

        ex = Exception("Test Exception")
        mocker.patch.object(backend.gcs_uploader, "upload_image").side_effect = ex

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        actual = backend.upload_image(image=test_image, is_thumbnail=True)
        assert actual is None

        # assert on sentry calls
        mock_call = [call(ex)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)


class TestDownloadImageMethod:
    """Tests for the download_image method."""

    @pytest.mark.asyncio
    async def test_returns_none_on_incorrect_extenstion(
        self, backend: WikimediaPotdBackend
    ) -> None:
        """Test download_image method returns None if the url image extension is not supported."""
        url_with_incorrect_extension = HttpUrl("http://www.test-image.com/image.txt")

        # call the backend method to download the image
        actual = await backend.download_image(url=url_with_incorrect_extension)

        assert actual is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_exception(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Test download_image method returns None http request raises exception."""
        image_url = HttpUrl("http://www.test-image.com/image.jpeg")
        http_error = HTTPError("Error fetching POTD")

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = http_error

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        # call the backend method to download the image
        actual = await backend.download_image(url=image_url)

        assert actual is None

        # assert on sentry calls
        mock_call = [call(http_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)

    @pytest.mark.asyncio
    async def test_returns_image_on_successful_download(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Test download_image method returns Image on successful download."""
        image_url = HttpUrl("http://www.test-image.com/image.png")

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=b"255",
            headers={"content-type": "image/png"},
            request=Request(method="GET", url=str(image_url)),
        )

        # call the backend method to download the image
        actual: Image | None = await backend.download_image(url=image_url)

        assert actual is not None
        assert actual.content == b"255"
        assert actual.content_type == "image/png"
