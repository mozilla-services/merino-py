# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wikimedia Picture of the Day backend."""

from pathlib import Path

import pytest
import freezegun
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from pydantic import HttpUrl
from httpx import AsyncClient, HTTPError, ReadTimeout, Request, Response
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.providers.rss.wikimedia_potd.backends.utils import WIKIMEDIA_REQUEST_HEADERS
from merino.providers.rss.wikimedia_potd.backends.wikimedia_potd import (
    WikimediaPictureOfTheDayBackend,
)
from merino.utils.gcs.models import Image

FEED_URL = "https://example.com/feed"
COMMONS_API_URL = "https://commons.example.com/w/api.php"

# The sample response is stored verbatim as JSON so the fixture matches the Featured API payload.
TEST_FEATURED_JSON = Path("tests/data/rss/wikimedia_potd/potd_featured.json").read_text(
    encoding="utf-8"
)

# A well-formed JSON response that is missing the "image" object, so parse_potd raises.
TEST_FEATURED_JSON_NO_IMAGE = "{}"


@pytest.fixture(name="gcs_uploader_mock")
def fixture_gcs_uploader_mock() -> GcsUploader:
    """Return a mock GcsUploader."""
    return MagicMock(spec=GcsUploader)


@pytest.fixture(name="backend")
def fixture_backend(
    statsd_mock, mocker: MockerFixture, gcs_uploader_mock
) -> WikimediaPictureOfTheDayBackend:
    """Return a WikimediaPictureOfTheDayBackend instance for testing."""
    return WikimediaPictureOfTheDayBackend(
        metrics_client=statsd_mock,
        http_client=mocker.AsyncMock(spec=AsyncClient),
        featured_api_base=FEED_URL,
        commons_api_url=COMMONS_API_URL,
        gcs_uploader=gcs_uploader_mock,
    )


@pytest.fixture(name="potd")
def fixture_potd() -> PictureOfTheDay:
    """Return a test PictureOfTheDay object."""
    return PictureOfTheDay(
        title="Test Potd",
        description="Test potd description",
        published_date="2026-06-07",
        thumbnail_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
        high_res_image_url=HttpUrl("https://www.test-image.com/image.jpeg"),
    )


class TestDownloadAndUploadPotdImagesMethod:
    """Tests for download_and_upload_potd_images method."""

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_download_and_upload_potd_images_returns_two_urls_when_successful(
        self, backend, potd, mocker: MockerFixture
    ) -> None:
        """Test that download_and_upload_potd_images method returns two urls when successful."""
        test_image = Image(content=b"255", content_type="Image/jpeg")

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mock the first download request response
        client_mock.get.side_effect = [
            Response(
                status_code=200,
                content=test_image.content,
                request=Request(method="GET", url=str(potd.thumbnail_image_url)),
                headers={"content-type": test_image.content_type},
            ),
            # mock the second download request response
            Response(
                status_code=200,
                content=test_image.content,
                request=Request(method="GET", url=str(potd.high_res_image_url)),
                headers={"content-type": test_image.content_type},
            ),
        ]

        expected_uploaded_url = HttpUrl("https://www.uploaded-test-image.com/image.jpeg")

        mocker.patch.object(backend, "upload_potd_image").return_value = expected_uploaded_url

        result = await backend.download_and_upload_potd_images(potd)

        assert result is not None
        thumbnail_url, hires_url = result

        assert thumbnail_url == expected_uploaded_url
        assert hires_url == expected_uploaded_url

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_download_and_upload_potd_images_propagates_error_when_one_download_call_fails(
        self, backend, potd, mocker: MockerFixture
    ) -> None:
        """Propagates the HTTP error when one of the image download requests fails."""
        test_image = Image(content=b"255", content_type="Image/jpeg")

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mock the first download request response
        client_mock.get.side_effect = [
            Response(
                status_code=200,
                content=test_image.content,
                request=Request(method="GET", url=str(potd.thumbnail_image_url)),
                headers={"content-type": test_image.content_type},
            ),
            # mock the second download request to return a 500 error
            Response(
                status_code=500,
                content=None,
                request=Request(method="GET", url=str(potd.high_res_image_url)),
            ),
        ]

        with pytest.raises(HTTPError):
            await backend.download_and_upload_potd_images(potd)

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_propagates_error_when_download_image_raises(
        self, backend, potd, mocker: MockerFixture
    ) -> None:
        """Propagates the error raised by download_potd_image."""
        mocker.patch.object(backend, "download_potd_image").side_effect = WikimediaPotdError(
            "download failed"
        )

        with pytest.raises(WikimediaPotdError):
            await backend.download_and_upload_potd_images(potd)

    @pytest.mark.asyncio
    async def test_download_and_upload_potd_images_propagates_error_when_upload_image_raises(
        self, backend, potd, mocker: MockerFixture
    ) -> None:
        """Propagates the error raised by upload_potd_image."""
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/jpeg"
        )
        mocker.patch.object(backend, "upload_potd_image").side_effect = WikimediaPotdError(
            "upload failed"
        )

        with pytest.raises(WikimediaPotdError):
            await backend.download_and_upload_potd_images(potd)


class TestOrchestratePictureOfTheDayUpload:
    """Tests for orchestrate_picture_of_the_day_upload method."""

    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_returns_false_when_no_feed_is_fetched(
        self, backend
    ) -> None:
        """Returns False when the fetch fails with a non-2xx status."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with a server error
        client_mock.get.return_value = Response(
            status_code=500,
            content=None,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_returns_false_when_parsing_fails(
        self, backend
    ) -> None:
        """Returns False when parsing fails on a response missing the image object."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)

        # mocking http client to respond with json that has no image object
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON_NO_IMAGE,
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_returns_false_when_downloading_image_fails(
        self, backend, mocker: MockerFixture
    ) -> None:
        """Returns False when downloading an image raises, caught at the orchestrator boundary."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )

        # mocking download_potd_image method to raise
        mocker.patch.object(backend, "download_potd_image").side_effect = WikimediaPotdError(
            "download failed"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False

    @freezegun.freeze_time("2026-06-24")
    @pytest.mark.asyncio
    async def test_upload_picture_of_the_day_returns_false_when_uploading_image_fails(
        self, backend, mocker: MockerFixture
    ) -> None:
        """Returns False when uploading an image raises, caught at the orchestrator boundary."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON,
            request=Request(method="GET", url=FEED_URL),
        )

        # mocking download method to return a valid value but raise on the upload method
        mocker.patch.object(backend, "download_potd_image").return_value = Image(
            content=b"255", content_type="Image/jpeg"
        )
        mocker.patch.object(backend, "upload_potd_image").side_effect = WikimediaPotdError(
            "upload failed"
        )

        result = await backend.upload_picture_of_the_day()
        assert result is False


class TestFetchPictureOfTheDayMethod:
    """Tests for fetch_picture_of_the_day method."""

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_fetch_potd_returns_json_on_success(
        self,
        backend: WikimediaPictureOfTheDayBackend,
    ) -> None:
        """Returns the parsed JSON dict and requests the dated Featured API url."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON.encode(),
            request=Request(method="GET", url=FEED_URL),
        )

        result = await backend.fetch_picture_of_the_day("en")

        assert result is not None
        assert result["image"]["title"] == "File:Milky Way over Sagittarius.jpg"
        client_mock.get.assert_called_once_with(
            f"{FEED_URL}/en/featured/2026/06/24", headers=WIKIMEDIA_REQUEST_HEADERS
        )

    @pytest.mark.asyncio
    async def test_fetch_potd_raises_for_empty_content(
        self,
        backend: WikimediaPictureOfTheDayBackend,
    ) -> None:
        """Raises WikimediaPotdError when the HTTP response body is empty."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=b"",
            request=Request(method="GET", url=FEED_URL),
        )

        with pytest.raises(WikimediaPotdError):
            await backend.fetch_picture_of_the_day("en")

    @pytest.mark.asyncio
    async def test_fetch_potd_propagates_http_error(
        self,
        backend: WikimediaPictureOfTheDayBackend,
    ) -> None:
        """Propagates the HTTP error when the request fails with a non-2xx status."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=500,
            request=Request(method="GET", url=FEED_URL),
        )

        with pytest.raises(HTTPError):
            await backend.fetch_picture_of_the_day("en")


class TestFetchPictureOfTheDayLanguage:
    """Tests that fetch_picture_of_the_day requests the given language."""

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_fetch_potd_uses_requested_language_in_url(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Builds the Featured API url with the requested language segment."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            content=TEST_FEATURED_JSON.encode(),
            request=Request(method="GET", url=FEED_URL),
        )

        await backend.fetch_picture_of_the_day("de")

        client_mock.get.assert_called_once_with(
            f"{FEED_URL}/de/featured/2026/06/24", headers=WIKIMEDIA_REQUEST_HEADERS
        )


class TestDiscoverLanguages:
    """Tests for the discover_languages method."""

    @pytest.mark.asyncio
    async def test_discover_languages_parses_commons_subpages(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Parses language codes from Commons subpages and prepends the default language."""
        commons_json = {
            "query": {
                "allpages": [
                    {"title": "Template:Potd/2026-06-24"},
                    {"title": "Template:Potd/2026-06-24 (de)"},
                    {"title": "Template:Potd/2026-06-24 (es)"},
                ]
            }
        }
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            json=commons_json,
            request=Request(method="GET", url=COMMONS_API_URL),
        )

        result = await backend.discover_languages("2026-06-24")

        assert result == ["en", "de", "es"]
        _, kwargs = client_mock.get.call_args
        assert kwargs["params"]["apprefix"] == "Potd/2026-06-24"
        assert kwargs["params"]["apnamespace"] == "10"

    @pytest.mark.asyncio
    async def test_discover_languages_does_not_duplicate_default(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Does not append the default language again when Commons already lists it."""
        commons_json = {
            "query": {
                "allpages": [
                    {"title": "Template:Potd/2026-06-24 (en)"},
                    {"title": "Template:Potd/2026-06-24 (de)"},
                ]
            }
        }
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200,
            json=commons_json,
            request=Request(method="GET", url=COMMONS_API_URL),
        )

        result = await backend.discover_languages("2026-06-24")

        assert result == ["en", "de"]

    @pytest.mark.asyncio
    async def test_discover_languages_falls_back_to_default_on_error(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Returns just the default language when the Commons request fails."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = HTTPError("commons down")

        result = await backend.discover_languages("2026-06-24")

        assert result == ["en"]


class TestFetchLocalizedDescriptions:
    """Tests for the fetch_localized_descriptions method."""

    @pytest.mark.asyncio
    async def test_skips_en_keeps_localized_drops_fallbacks(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Skips "en", keeps genuinely localized text, and drops English fallbacks."""
        de_data = {"image": {"description": {"lang": "de", "text": "Deutscher Text"}}}
        # fr has no authored description, so the API returns the English fallback.
        fr_fallback = {"image": {"description": {"lang": "en", "text": "English text"}}}

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = [
            Response(status_code=200, json=de_data, request=Request(method="GET", url=FEED_URL)),
            Response(
                status_code=200, json=fr_fallback, request=Request(method="GET", url=FEED_URL)
            ),
        ]

        result = await backend.fetch_localized_descriptions(["en", "de", "fr"])

        # "en" is never fetched or stored; only "de" is fetched and both requests are localized
        assert result == {"de": "Deutscher Text"}

    @pytest.mark.asyncio
    async def test_skips_language_when_fetch_raises(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Skips a language whose fetch raises, keeping the rest of the map intact."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = HTTPError("boom")

        result = await backend.fetch_localized_descriptions(["en", "de"])

        assert result == {}

    @pytest.mark.asyncio
    async def test_drops_language_with_empty_description_text(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Does not store a language whose description text is empty."""
        de_empty = {"image": {"description": {"lang": "de", "text": ""}}}

        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.return_value = Response(
            status_code=200, json=de_empty, request=Request(method="GET", url=FEED_URL)
        )

        result = await backend.fetch_localized_descriptions(["en", "de"])

        assert result == {}

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_fetch_potd_retries_transient_error_then_succeeds(
        self,
        backend: WikimediaPictureOfTheDayBackend,
    ) -> None:
        """Retries a transient read timeout and returns the response once the fetch succeeds."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = [
            ReadTimeout("transient"),
            ReadTimeout("transient"),
            Response(
                status_code=200,
                content=TEST_FEATURED_JSON.encode(),
                request=Request(method="GET", url=FEED_URL),
            ),
        ]

        result = await backend.fetch_picture_of_the_day()

        assert result["image"]["title"] == "File:Milky Way over Sagittarius.jpg"
        assert client_mock.get.call_count == 3

    @pytest.mark.asyncio
    @freezegun.freeze_time("2026-06-24")
    async def test_fetch_potd_reraises_after_exhausting_retries(
        self,
        backend: WikimediaPictureOfTheDayBackend,
    ) -> None:
        """Reraises the underlying error after exhausting the configured attempts."""
        client_mock: AsyncMock = cast(AsyncMock, backend.http_client)
        client_mock.get.side_effect = ReadTimeout("always down")

        with pytest.raises(ReadTimeout):
            await backend.fetch_picture_of_the_day()

        assert client_mock.get.call_count == settings.rss_providers.wikimedia_potd.retry_count


class TestGcsUploadVerification:
    """Tests that a swallowed GCS write is surfaced as a WikimediaPotdError.

    GcsUploader.upload_content logs and swallows storage errors, so the POTD backend
    verifies the object actually landed in the bucket after uploading.
    """

    def test_upload_potd_image_raises_when_object_not_in_bucket(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Raises when the image is absent from the bucket after a (swallowed) failed upload."""
        # upload_image still returns a public url even though the write failed and was swallowed.
        backend.gcs_uploader.upload_image.return_value = (  # type: ignore[attr-defined]
            "https://cdn/wikimedia_potd/image.png"
        )
        # the object is not actually present in the bucket.
        backend.gcs_uploader.get_file_by_name.return_value = None  # type: ignore[attr-defined]

        with pytest.raises(WikimediaPotdError):
            backend.upload_potd_image(
                image=Image(content=b"255", content_type="image/png"), is_thumbnail=True
            )

    def test_upload_potd_image_forwards_cache_control_to_uploader(
        self, backend: WikimediaPictureOfTheDayBackend
    ) -> None:
        """Forwards the configured cache_control setting to gcs_uploader.upload_image."""
        backend.gcs_uploader.upload_image.return_value = (  # type: ignore[attr-defined]
            "https://cdn/wikimedia_potd/image.png"
        )
        # the object is present in the bucket so the upload does not raise.
        backend.gcs_uploader.get_file_by_name.return_value = MagicMock()  # type: ignore[attr-defined]

        backend.upload_potd_image(
            image=Image(content=b"255", content_type="image/png"), is_thumbnail=True
        )

        _, kwargs = backend.gcs_uploader.upload_image.call_args  # type: ignore[attr-defined]
        assert kwargs["cache_control"] == settings.rss_providers.wikimedia_potd.cache_control

    def test_upload_potd_manifest_raises_when_object_not_in_bucket(
        self, backend: WikimediaPictureOfTheDayBackend, potd: PictureOfTheDay
    ) -> None:
        """Raises when the manifest is absent from the bucket after a (swallowed) failed upload."""
        # the object is not actually present in the bucket after the (swallowed) failed upload.
        backend.gcs_uploader.get_file_by_name.return_value = None  # type: ignore[attr-defined]

        with pytest.raises(WikimediaPotdError):
            backend.upload_potd_manifest(potd)
