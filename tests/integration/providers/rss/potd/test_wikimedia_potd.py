# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Picture of the Day Provider."""

import pytest
import freezegun
import orjson

from typing import cast
from pydantic import HttpUrl
from unittest.mock import call, AsyncMock, Mock
from httpx import AsyncClient, HTTPError, Request, Response
from pytest_mock import MockerFixture
from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
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
        backend.upload_potd_image(image=test_image, is_thumbnail=True)

        # get the blob (image) from the same bucket assigned to the gcs_uploader instance of the backend object
        blobs_in_bucket = list(gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs())

        # should be only one blob (thumbnail image)
        assert len(blobs_in_bucket) == 1
        assert blobs_in_bucket[0].name == "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"

    def test_captures_sentry_exception(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Test upload_image method successfully captures sentry exception."""
        test_image = Image(content=b"", content_type="Image/jpeg")

        ex = Exception("Test Exception")
        mocker.patch.object(backend.gcs_uploader, "upload_image").side_effect = ex

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        actual = backend.upload_potd_image(image=test_image, is_thumbnail=True)
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
        actual = await backend.download_potd_image(url=url_with_incorrect_extension)

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
        actual = await backend.download_potd_image(url=image_url)

        assert actual is None

        # assert on sentry calls
        mock_call = [call(http_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)

    @pytest.mark.asyncio
    async def test_returns_image_on_successful_download(
        self, backend: WikimediaPotdBackend
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
        actual: Image | None = await backend.download_potd_image(url=image_url)

        assert actual is not None
        assert actual.content == b"255"
        assert actual.content_type == "image/png"


class TestBuildAndUploadPotdMethod:
    """Tests for build_and_upload_potd method."""

    @freezegun.freeze_time("2026-06-07")
    @pytest.mark.asyncio
    async def test_build_and_upload_potd_returns_true_on_success(
        self, backend: WikimediaPotdBackend, gcs_storage_client, gcs_storage_bucket
    ) -> None:
        """Returns True on successful build and upload of an PictureOfTheDay object to the gcs bucket."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        # call the method to build and upload the potd jsob blob
        actual = backend.build_and_upload_potd(potd=potd)

        # get the potd manifest json blob from the bucket
        potd_manifest_blob = list(
            gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs()
        )[0]

        # download the above manifest blob as json
        blob_json = orjson.loads(potd_manifest_blob.download_as_text())

        assert actual is True
        assert potd_manifest_blob.name == "rss/wikimedia_potd/POTD_2026-06-07.json"
        assert blob_json["title"] == potd.title
        assert blob_json["description"] == potd.description
        assert blob_json["published_date"] == potd.published_date
        assert blob_json["high_res_image_url"] == str(potd.high_res_image_url)
        assert blob_json["thumbnail_image_url"] == str(potd.thumbnail_image_url)

    @pytest.mark.asyncio
    async def test_build_and_upload_potd_returns_false_on_upload_error(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Returns False on upload error."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        upload_error = Exception("Failed upload content.")

        # mock the upload_content method to return the upload_error
        backend.gcs_uploader = Mock(spec=GcsUploader)
        backend.gcs_uploader.upload_content.side_effect = upload_error

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        # call the method to build and upload the potd jsob blob
        actual = backend.build_and_upload_potd(potd=potd)

        assert actual is False
        # assert on sentry calls
        mock_call = [call(upload_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)


class TestFetchPotdFromGcsBucketMethod:
    """Tests for fetch_potd_from_gcs_bucket method."""

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_potd_instance_on_success(
        self, backend: WikimediaPotdBackend
    ) -> None:
        """Returns a PictureOfTheDay object on successful fetch from the bucket."""
        expected = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        # call the method to build and upload the potd json blob to the bucket
        backend.build_and_upload_potd(potd=expected)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is not None
        assert actual.title == expected.title
        assert actual.description == expected.description
        assert actual.published_date == expected.published_date
        assert actual.high_res_image_url == expected.high_res_image_url
        assert actual.thumbnail_image_url == expected.thumbnail_image_url

    def test_fetch_potd_from_gcs_bucket_returns_none_when_path_has_stale_date(
        self, backend: WikimediaPotdBackend
    ) -> None:
        """Returns None when date in the blob path is incorrect (stale)."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        # call the method to build and upload the potd json blob to the bucket with a stale date
        with freezegun.freeze_time("2026-06-07"):
            backend.build_and_upload_potd(potd=potd)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_none_when_blob_retrieval_returns_an_error(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Returns None when gcs_uploader.get_file_by_name() returns an error."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        blob_retrieval_error = Exception("Failed to retrieve blob.")
        # mock the get_file_by_name method to return the blob_retrieval_error
        backend.gcs_uploader = Mock(spec=GcsUploader)
        backend.gcs_uploader.get_file_by_name.side_effect = blob_retrieval_error

        # call the method to build and upload the potd json blob to the bucket with a stale date
        backend.build_and_upload_potd(potd=potd)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None
        # assert on sentry calls
        mock_call = [call(blob_retrieval_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_none_when_blob_download_returns_an_error(
        self, backend: WikimediaPotdBackend, mocker: MockerFixture
    ) -> None:
        """Returns None when gcs_uploader.download_as_text() returns an error"""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        blob_download_error = Exception("Failed to download blob.")

        # mock the download_as_text() method for the imported Blob class in gcs_uploader.py module
        mocker.patch(
            "merino.utils.gcs.gcs_uploader.Blob.download_as_text"
        ).side_effect = blob_download_error

        # call the method to build and upload the potd json blob to the bucket with a stale date
        backend.build_and_upload_potd(potd=potd)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None
        # assert on sentry calls
        mock_call = [call(blob_download_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)
