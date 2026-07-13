# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Picture of the Day Provider."""

from pathlib import Path

import pytest
import freezegun
import orjson

from typing import cast
from pydantic import HttpUrl
from unittest.mock import call, AsyncMock, Mock
from httpx import AsyncClient, HTTPError, Request, Response
from pytest_mock import MockerFixture
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPictureOfTheDayBackend,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image

FEED_URL = "https://api.wikimedia.org/feed/v1/wikipedia/en/featured"

# The sample response is stored verbatim as JSON so the fixture matches the Featured API payload.
TEST_FEATURED_JSON = Path("tests/data/rss/wikimedia_potd/potd_featured.json").read_text(
    encoding="utf-8"
)

# A well-formed JSON response that is missing the "image" object, so parse_potd raises.
TEST_FEATURED_JSON_NO_IMAGE = "{}"


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock, mocker: MockerFixture, gcs_storage_client, gcs_storage_bucket
) -> WikimediaPictureOfTheDayBackend:
    """Return a WikimediaPictureOfTheDayBackend instance for testing."""
    return WikimediaPictureOfTheDayBackend(
        metrics_client=statsd_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        feed_url="https://example.com/feed",
        gcs_uploader=GcsUploader(
            destination_gcp_project=gcs_storage_client.project,
            destination_bucket_name=gcs_storage_bucket.name,
            destination_cdn_hostname="test-cdn-name",
        ),
    )


class TestUploadPictureOfTheDayMethod:
    """Tests for upload_picture_of_the_day_upload method."""

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_true_on_success(
        self,
        backend: WikimediaPictureOfTheDayBackend,
        gcs_storage_client,
        gcs_storage_bucket,
        mocker: MockerFixture,
    ) -> None:
        """Returns True on successful upload orchestration of the PictureOfTheDay object to the gcs bucket."""
        # mock get request for the Featured API to return TEST_FEATURED_JSON
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )

        # mock download_and_upload_potd_images(potd) returns
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/png"
        )

        # call the orchestrate method
        result = await backend.upload_picture_of_the_day()
        assert result is True

        # call the backend method to fetch the potd manifest from the gcs bucket
        potd_manifest = backend.fetch_potd_from_gcs_bucket()

        assert potd_manifest is not None
        assert isinstance(potd_manifest, PictureOfTheDay)
        assert potd_manifest.title == "Wikimedia Commons Picture of the Day for June 24"
        assert potd_manifest.published_date == "2026-06-24"
        assert (
            str(potd_manifest.thumbnail_image_url)
            == "https://test-cdn-name/rss/wikimedia_potd/POTD_2026-06-24_thumbnail.png"
        )
        assert (
            str(potd_manifest.high_res_image_url)
            == "https://test-cdn-name/rss/wikimedia_potd/POTD_2026-06-24_hi_res.png"
        )
        assert "Sagittarius" in potd_manifest.description
        assert potd_manifest.author == "Test Artist"
        assert str(potd_manifest.file_page) == "https://commons.wikimedia.org/wiki/File:Test.jpg"
        assert potd_manifest.license_label == "CC BY-SA 4.0"
        assert str(potd_manifest.license_link) == "https://creativecommons.org/licenses/by-sa/4.0"

        # fetch the uploaded blobs (two images and one json manifest object)
        potd_blobs = list(gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs())

        assert len(potd_blobs) == 3
        assert potd_blobs[0].name == "rss/wikimedia_potd/POTD_2026-06-24.json"
        assert potd_blobs[1].name == "rss/wikimedia_potd/POTD_2026-06-24_hi_res.png"
        assert potd_blobs[2].name == "rss/wikimedia_potd/POTD_2026-06-24_thumbnail.png"

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_when_feed_fetch_fails(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Returns False when fetch_picture_of_the_day raises."""
        mocker.patch.object(backend, "fetch_picture_of_the_day").side_effect = WikimediaPotdError(
            "feed fetch failed"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-25")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_when_potd_parsing_fails(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Returns False when the response has no image object, causing parse_potd to raise."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON_NO_IMAGE,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_when_image_download_fails(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Returns False when download_potd_image raises, propagating up to the orchestrator boundary."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )
        mocker.patch.object(backend, "download_potd_image").side_effect = WikimediaPotdError(
            "image download failed"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_when_manifest_upload_fails(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Returns False when upload_potd_manifest raises."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/png"
        )
        mocker.patch.object(backend, "upload_potd_manifest").side_effect = WikimediaPotdError(
            "manifest upload failed"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_when_gcs_upload_fails(
        self,
        backend: WikimediaPictureOfTheDayBackend,
        gcs_storage_client,
        gcs_storage_bucket,
        mocker: MockerFixture,
    ) -> None:
        """A failed GCS upload must be reported as failure and must not publish a manifest."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )
        # Images "download" fine; only the GCS upload should fail.
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/png"
        )

        # Simulate a real GCS write failure at the storage layer, so the real
        # GcsUploader.upload_content path runs.
        mocker.patch(
            "google.cloud.storage.Blob.upload_from_string",
            side_effect=Exception("GCS upload failed"),
        )

        result = await backend.upload_picture_of_the_day()

        # Intended contract: the upload failed, so orchestration reports failure.
        assert result is False

        # Intended contract: no manifest is published pointing at images that never uploaded.
        assert backend.fetch_potd_from_gcs_bucket() is None
        blob_names = [
            blob.name
            for blob in gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs()
        ]
        assert "rss/wikimedia_potd/POTD_2026-06-24.json" not in blob_names

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_upload_returns_false_and_captures_sentry_exception_on_unexpected_error(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Returns False and captures the exception via Sentry when an unexpected error is raised."""
        unexpected_error = Exception("Unexpected error during orchestration")
        mocker.patch.object(backend, "fetch_picture_of_the_day").side_effect = unexpected_error

        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False
        sentry_capture.assert_called_once_with(unexpected_error)


class TestFetchPictureOfTheDayMethod:
    """Tests for the fetch_picture_of_the_day method."""

    @pytest.mark.asyncio
    async def test_fetch_picture_of_the_day_raises_on_invalid_json(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Raises WikimediaPotdError when the Featured API returns a non-JSON body."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=b"<html>not json</html>",
            request=Request(method="GET", url=FEED_URL),
        )

        with pytest.raises(WikimediaPotdError):
            await backend.fetch_picture_of_the_day()


class TestUploadImageMethod:
    """Tests for the upload_image method."""

    @freezegun.freeze_time("2026-06-07")
    def test_thumbnail_upload_only_success(
        self, backend: WikimediaPictureOfTheDayBackend, gcs_storage_client, gcs_storage_bucket
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

    def test_propagates_upload_error(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Test upload_image method propagates the underlying upload error to the caller."""
        test_image = Image(content=b"", content_type="Image/jpeg")

        ex = Exception("Test Exception")
        mocker.patch.object(backend.gcs_uploader, "upload_image").side_effect = ex

        with pytest.raises(Exception, match="Test Exception"):
            backend.upload_potd_image(image=test_image, is_thumbnail=True)


class TestDownloadImageMethod:
    """Tests for the download_image method."""

    @pytest.mark.asyncio
    async def test_raises_on_incorrect_extenstion(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Test download_image method raises if the url image extension is not supported."""
        url_with_incorrect_extension = HttpUrl("http://www.test-image.com/image.txt")

        # call the backend method to download the image
        with pytest.raises(WikimediaPotdError):
            await backend.download_potd_image(url=url_with_incorrect_extension)

    @pytest.mark.asyncio
    async def test_propagates_http_exception(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Test download_image method propagates the HTTP error raised by the request."""
        image_url = HttpUrl("http://www.test-image.com/image.jpeg")
        http_error = HTTPError("Error fetching POTD")

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = http_error

        # call the backend method to download the image
        with pytest.raises(HTTPError, match="Error fetching POTD"):
            await backend.download_potd_image(url=image_url)

    @pytest.mark.asyncio
    async def test_returns_image_on_successful_download(
        self, backend: WikimediaPictureOfTheDayBackend
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
    async def test_build_and_upload_potd_succeeds(
        self, backend: WikimediaPictureOfTheDayBackend, gcs_storage_client, gcs_storage_bucket
    ) -> None:
        """Successfully builds and uploads a PictureOfTheDay object to the gcs bucket."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        # call the method to build and upload the potd jsob blob
        backend.upload_potd_manifest(potd=potd)

        # get the potd manifest json blob from the bucket
        potd_manifest_blob = list(
            gcs_storage_client.get_bucket(gcs_storage_bucket.name).list_blobs()
        )[0]

        # download the above manifest blob as json
        blob_json = orjson.loads(potd_manifest_blob.download_as_text())

        assert potd_manifest_blob.name == "rss/wikimedia_potd/POTD_2026-06-07.json"
        assert blob_json["title"] == potd.title
        assert blob_json["description"] == potd.description
        assert blob_json["published_date"] == potd.published_date
        assert blob_json["high_res_image_url"] == str(potd.high_res_image_url)
        assert blob_json["thumbnail_image_url"] == str(potd.thumbnail_image_url)

    @pytest.mark.asyncio
    async def test_build_and_upload_potd_propagates_upload_error(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Propagates the underlying error on upload failure."""
        potd = PictureOfTheDay(
            title="Test Potd",
            description="Test potd description",
            published_date="2026-06-7",
            high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
            thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        )

        upload_error = Exception("Failed upload content.")

        # mock the upload_content method to raise the upload_error
        backend.gcs_uploader = Mock(spec=GcsUploader)
        backend.gcs_uploader.upload_content.side_effect = upload_error

        # call the method to build and upload the potd jsob blob
        with pytest.raises(Exception, match="Failed upload content."):
            backend.upload_potd_manifest(potd=potd)


class TestFetchPotdFromGcsBucketMethod:
    """Tests for fetch_potd_from_gcs_bucket method."""

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_potd_instance_on_success(
        self, backend: WikimediaPictureOfTheDayBackend
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
        backend.upload_potd_manifest(potd=expected)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is not None
        assert actual.title == expected.title
        assert actual.description == expected.description
        assert actual.published_date == expected.published_date
        assert actual.high_res_image_url == expected.high_res_image_url
        assert actual.thumbnail_image_url == expected.thumbnail_image_url

    def test_fetch_potd_from_gcs_bucket_returns_none_when_path_has_stale_date(
        self, backend: WikimediaPictureOfTheDayBackend
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
            backend.upload_potd_manifest(potd=potd)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_none_when_blob_retrieval_returns_an_error(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
    ) -> None:
        """Returns None when gcs_uploader.get_file_by_name() returns an error."""
        sentry_capture = mocker.patch(
            "merino.providers.rss.wikimedia_potd.backends.wikimedia_potd.sentry_sdk.capture_exception"
        )

        blob_retrieval_error = Exception("Failed to retrieve blob.")
        # mock the get_file_by_name method to return the blob_retrieval_error
        backend.gcs_uploader = Mock(spec=GcsUploader)
        backend.gcs_uploader.get_file_by_name.side_effect = blob_retrieval_error

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None
        # assert on sentry calls
        mock_call = [call(blob_retrieval_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)

    @freezegun.freeze_time("2026-06-07")
    def test_fetch_potd_from_gcs_bucket_returns_none_when_blob_download_returns_an_error(
        self, backend: WikimediaPictureOfTheDayBackend, mocker: MockerFixture
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
        backend.upload_potd_manifest(potd=potd)

        # call the method to fetch the uploaded potd json blob from the bucket
        actual = backend.fetch_potd_from_gcs_bucket()

        assert actual is None
        # assert on sentry calls
        mock_call = [call(blob_download_error)]
        assert sentry_capture.call_count == 1
        sentry_capture.assert_has_calls(mock_call)
