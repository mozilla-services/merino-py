# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon backend module."""

import hashlib
import orjson
import logging
from pydantic import HttpUrl
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, HTTPStatusError, Request, Response
from pytest_mock import MockerFixture
from typing import Any, cast
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.gcs.models import Image
from tests.types import FilterCaplogFixture
from pytest import LogCaptureFixture
from merino.configs import settings

from merino.providers.suggest.finance.backends.polygon.backend import PolygonBackend
from merino.providers.suggest.finance.backends.protocol import (
    FinanceManifest,
    GetManifestResultCode,
    TickerSummary,
)

URL_SINGLE_TICKER_SNAPSHOT = settings.polygon.url_single_ticker_snapshot
URL_SINGLE_TICKER_OVERVIEW = settings.polygon.url_single_ticker_overview


@pytest.fixture(name="mock_gcs_uploader")
def fixture_mock_gcs_uploader(mocker) -> GcsUploader:
    """Create a mock GcsUploader instance."""
    mock_uploader = MagicMock()

    mock_uploader.bucket_name = "test-bucket"
    mock_uploader.cdn_hostname = "cdn.example.com"

    mock_uploader._get_public_url.return_value = "https://cdn.example.com/fake.png"
    mock_uploader.upload_image.return_value = "https://cdn.example.com/fake.png"

    mock_blob = mocker.MagicMock()
    mock_bucket = mocker.MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_storage_client = mocker.MagicMock()
    mock_storage_client.bucket.return_value = mock_bucket
    mock_uploader.storage_client = mock_storage_client

    return cast(GcsUploader, mock_uploader)


@pytest.fixture(name="polygon_parameters")
def fixture_polygon_parameters(
    mocker: MockerFixture, statsd_mock: Any, mock_gcs_uploader
) -> dict[str, Any]:
    """Create constructor parameters for Polygon backend module."""
    return {
        "api_key": "api_key",
        "metrics_client": statsd_mock,
        "http_client": mocker.AsyncMock(spec=AsyncClient),
        "metrics_sample_rate": 1,
        "url_param_api_key": "apiKey",
        "url_single_ticker_snapshot": URL_SINGLE_TICKER_SNAPSHOT,
        "url_single_ticker_overview": URL_SINGLE_TICKER_OVERVIEW,
        "gcs_uploader": mock_gcs_uploader,
    }


@pytest.fixture(name="polygon")
def fixture_polygon(
    polygon_parameters: dict[str, Any],
    mocker: MockerFixture,
) -> PolygonBackend:
    """Create a Polygon backend module object."""
    mock_filemanager = mocker.MagicMock()
    mocker.patch(
        "merino.providers.suggest.finance.backends.polygon.backend.PolygonFilemanager",
        return_value=mock_filemanager,
    )
    return PolygonBackend(**polygon_parameters)


@pytest.fixture(name="single_ticker_snapshot_response")
def fixture_single_ticker_snapshot_response() -> dict[str, Any]:
    """Sample response for single ticker snapshot request."""
    return {
        "request_id": "657e430f1ae768891f018e08e03598d8",
        "status": "OK",
        "ticker": {
            "day": {
                "c": 120.4229,
                "h": 120.53,
                "l": 118.81,
                "o": 119.62,
                "v": 28727868,
                "vw": 119.725,
            },
            "lastQuote": {"P": 120.47, "S": 4, "p": 120.46, "s": 8, "t": 1605195918507251700},
            "lastTrade": {
                "c": [14, 41],
                "i": "4046",
                "p": 120.47,
                "s": 236,
                "t": 1605195918306274000,
                "x": 10,
            },
            "min": {
                "av": 28724441,
                "c": 120.4201,
                "h": 120.468,
                "l": 120.37,
                "n": 762,
                "o": 120.435,
                "t": 1684428720000,
                "v": 270796,
                "vw": 120.4129,
            },
            "prevDay": {
                "c": 119.49,
                "h": 119.63,
                "l": 116.44,
                "o": 117.19,
                "v": 110597265,
                "vw": 118.4998,
            },
            "ticker": "AAPL",
            "todaysChange": 0.98,
            "todaysChangePerc": 0.82,
            "updated": 1605195918306274000,
        },
    }


@pytest.fixture(name="ticker_summary")
def fixture_ticker_summary() -> TickerSummary:
    """Create a ticker summary object for AAPL."""
    # these values are based on the above single_ticker_snapshot_response fixture.
    return TickerSummary(
        ticker="AAPL",
        name="Apple Inc.",
        last_price="$120.47 USD",
        todays_change_perc="0.82",
        query="AAPL stock",
        image_url=None,
    )


@pytest.fixture
def sample_image() -> Image:
    """Return a sample image object"""
    return Image(content=b"fake-image-bytes", content_type="image/png")


@pytest.mark.asyncio
async def test_fetch_ticker_snapshot_success(
    polygon: PolygonBackend, single_ticker_snapshot_response: dict[str, Any]
) -> None:
    """Test fetch_ticker_snapshot method. Should return valid response json."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(single_ticker_snapshot_response),
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    expected = single_ticker_snapshot_response
    actual = await polygon.fetch_ticker_snapshot(ticker)

    assert actual is not None
    assert actual == expected
    assert actual["ticker"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_fetch_ticker_snapshot_failure_for_http_500(
    polygon: PolygonBackend,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test fetch_ticker_snapshot method. Should raise for status on HTTPStatusError 500."""
    caplog.set_level(logging.WARNING)

    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=500,
        content=b"",
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    _ = await polygon.fetch_ticker_snapshot(ticker)

    records = filter_caplog(
        caplog.records, "merino.providers.suggest.finance.backends.polygon.backend"
    )

    assert len(caplog.records) == 1

    assert records[0].message.startswith("Polygon request error")
    assert "500 Internal Server Error" in records[0].message


@pytest.mark.asyncio
async def test_get_ticker_summary_success(
    polygon: PolygonBackend,
    single_ticker_snapshot_response: dict[str, Any],
    ticker_summary: TickerSummary,
) -> None:
    """Test get_ticker_summary method. Should return valid TickerSummary object."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(single_ticker_snapshot_response),
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    expected = ticker_summary
    actual = await polygon.get_ticker_summary(ticker, ticker_summary.image_url)

    assert actual is not None
    assert actual == expected


@pytest.mark.asyncio
async def test_get_ticker_summary_failure_returns_none(polygon: PolygonBackend) -> None:
    """Test get_ticker_summary. Should return None when snapshot request returns HTTP 500."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)

    ticker = "AAPL"
    base_url = "https://api.polygon.io/apiKey=api_key"
    snapshot_endpoint = URL_SINGLE_TICKER_SNAPSHOT.format(ticker=ticker)

    client_mock.get.return_value = Response(
        status_code=500,
        content=b"",
        request=Request(method="GET", url=(f"{base_url}{snapshot_endpoint}")),
    )

    actual = await polygon.get_ticker_summary(ticker, None)

    assert actual is None


@pytest.mark.asyncio
async def test_get_ticker_image_url_success(polygon: PolygonBackend) -> None:
    """Test get_ticker_image_url returns the logo_url when present in the response."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)
    ticker = "AAPL"
    image_url = "https://example.com/logo.png"

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps({"results": {"branding": {"logo_url": image_url}}}),
        request=Request(method="GET", url="mock-url"),
    )

    result = await polygon.get_ticker_image_url(ticker)
    assert result == image_url


@pytest.mark.asyncio
async def test_get_ticker_image_url_missing_logo_url(polygon: PolygonBackend) -> None:
    """Test get_ticker_image_url returns None when logo_url is missing from response."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)
    ticker = "AAPL"

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(
            {
                "results": {
                    "branding": {
                        # no "logo_url"
                    }
                }
            }
        ),
        request=Request(method="GET", url="mock-url"),
    )

    result = await polygon.get_ticker_image_url(ticker)
    assert result is None


@pytest.mark.asyncio
async def test_get_ticker_image_url_http_error(polygon: PolygonBackend):
    """Test get_ticker_image_url returns None and logs error on HTTP failure."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)
    ticker = "AAPL"

    # Simulate a failed response
    response = Response(
        status_code=500,
        content=b"{}",
        request=Request("GET", f"https://api.polygon.io/v3/reference/tickers/{ticker}"),
    )

    client_mock.get.side_effect = HTTPStatusError(
        "Server Error", request=response.request, response=response
    )

    result = await polygon.get_ticker_image_url(ticker)
    assert result is None


@pytest.mark.asyncio
async def test_get_ticker_image_url_invalid_response_structure(polygon: PolygonBackend) -> None:
    """Test get_ticker_image_url returns None when branding or results keys are missing."""
    client_mock: AsyncMock = cast(AsyncMock, polygon.http_client)
    ticker = "AAPL"

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps({"unexpected": {"data": "bad format"}}),
        request=Request(method="GET", url="mock-url"),
    )

    result = await polygon.get_ticker_image_url(ticker)
    assert result is None


@pytest.mark.asyncio
async def test_download_ticker_image_success(polygon: PolygonBackend, mocker):
    """Test download_ticker_image returns Image object on valid download."""
    image_url = "https://example.com/logo.png"
    image_content = b"\x89PNG\r\n\x1a\n..."

    mocker.patch.object(polygon, "get_ticker_image_url", return_value=image_url)

    mock_response = Response(
        status_code=200,
        content=image_content,
        headers={"Content-Type": "image/png"},
        request=Request(method="GET", url=image_url),
    )

    client_mock = cast(AsyncMock, polygon.http_client)
    client_mock.get.return_value = mock_response

    image = await polygon.download_ticker_image("AAPL")

    assert isinstance(image, Image)
    assert image.content == image_content
    assert image.content_type == "image/png"


@pytest.mark.asyncio
async def test_download_ticker_image_returns_none_if_no_image_url(polygon: PolygonBackend, mocker):
    """Test download_ticker_image returns None if get_ticker_image_url returns None."""
    mocker.patch.object(polygon, "get_ticker_image_url", return_value=None)

    result = await polygon.download_ticker_image("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_download_ticker_image_failure(polygon: PolygonBackend, mocker):
    """Test download_ticker_image returns None if image download fails."""
    image_url = "https://example.com/logo.png"
    mocker.patch.object(polygon, "get_ticker_image_url", return_value=image_url)

    response = Response(
        status_code=500,
        content=b"server error",
        request=Request("GET", image_url),
    )

    client_mock = cast(AsyncMock, polygon.http_client)
    client_mock.get.side_effect = HTTPStatusError(
        "Image download failed", request=response.request, response=response
    )

    result = await polygon.download_ticker_image("AAPL")

    assert result is None


@pytest.mark.asyncio
async def test_download_ticker_image_with_missing_content_type(polygon: PolygonBackend, mocker):
    """Test download_ticker_image returns 'image/unknown' if Content-Type is missing."""
    image_url = "https://example.com/logo.png"
    image_content = b"some-binary-content"

    mocker.patch.object(polygon, "get_ticker_image_url", return_value=image_url)

    mock_response = Response(
        status_code=200,
        content=image_content,
        headers={},  # No Content-Type
        request=Request(method="GET", url=image_url),
    )

    client_mock = cast(AsyncMock, polygon.http_client)
    client_mock.get.return_value = mock_response

    image = await polygon.download_ticker_image("AAPL")

    assert isinstance(image, Image)
    assert image.content == image_content
    assert image.content_type == "image/svg+xml"


@pytest.mark.asyncio
async def test_upload_ticker_images_skips_none_image_and_uploads_other(
    polygon: PolygonBackend, sample_image, mock_gcs_uploader, mocker
):
    """Test that `bulk_download_and_upload_ticker_images` skips a ticker when its image is None"""
    ticker_skipped = "AAPL"
    ticker_uploaded = "GOOGL"

    # AAPL returns None, GOOGL returns an image
    polygon_mock_download = mocker.patch.object(
        polygon, "download_ticker_image", side_effect=[None, sample_image]
    )

    content_hash = hashlib.sha256(sample_image.content).hexdigest()
    content_len = len(sample_image.content)
    destination_name = f"polygon/{content_hash}_{content_len}.png"
    expected_url = f"https://cdn.example.com/{destination_name}"

    upload_image_mock = mocker.patch.object(
        mock_gcs_uploader, "upload_image", return_value=expected_url
    )

    result = await polygon.bulk_download_and_upload_ticker_images(
        [ticker_skipped, ticker_uploaded],
    )

    assert result == {ticker_uploaded: expected_url}
    assert polygon_mock_download.call_count == 2
    polygon_mock_download.assert_any_await(ticker_skipped)
    polygon_mock_download.assert_any_await(ticker_uploaded)
    upload_image_mock.assert_called_once()


@pytest.mark.asyncio
async def test_upload_ticker_images_uploads_if_not_exists(
    polygon: PolygonBackend,
    sample_image: Image,
    mock_gcs_uploader: GcsUploader,
    mocker,
):
    """Test that `bulk_download_and_upload_ticker_images` uploads an image when it does not already exist in GCS."""
    mocker.patch.object(polygon, "download_ticker_image", return_value=sample_image)

    content_hash = hashlib.sha256(sample_image.content).hexdigest()
    content_len = len(sample_image.content)
    destination = f"polygon/{content_hash}_{content_len}.png"
    expected_url = f"https://cdn.example.com/{destination}"

    upload_image_mock = mocker.patch.object(
        mock_gcs_uploader, "upload_image", return_value=expected_url
    )

    result = await polygon.bulk_download_and_upload_ticker_images(["AAPL"])

    assert result == {"AAPL": expected_url}
    upload_image_mock.assert_called_once()


@pytest.mark.asyncio
async def test_upload_ticker_images_upload_fails(
    polygon: PolygonBackend,
    sample_image: Image,
    mock_gcs_uploader: GcsUploader,
    mocker,
):
    """Test that `bulk_download_and_upload_ticker_images` skips the ticker if upload_image raises an exception."""
    mocker.patch.object(polygon, "download_ticker_image", return_value=sample_image)
    upload_image_mock = mocker.patch.object(
        mock_gcs_uploader, "upload_image", side_effect=RuntimeError("upload failed")
    )

    result = await polygon.bulk_download_and_upload_ticker_images(["AAPL"])

    assert result == {}
    upload_image_mock.assert_called_once()


def test_build_finance_manifest_valid():
    """Test that build_finance_manifest creates a valid FinanceManifest with uppercased tickers
    and valid URLs
    """
    input_data = {
        "aapl": "https://cdn.example.com/aapl.png",
        "googl": "https://cdn.example.com/googl.png",
    }

    manifest = PolygonBackend.build_finance_manifest(input_data)

    assert isinstance(manifest, FinanceManifest)
    assert set(manifest.tickers.keys()) == {"AAPL", "GOOGL"}
    assert manifest.tickers["AAPL"] == HttpUrl("https://cdn.example.com/aapl.png")


def test_build_finance_manifest_already_uppercase():
    """Test that build_finance_manifest preserves uppercase tickers correctly."""
    input_data = {
        "AAPL": "https://cdn.example.com/aapl.png",
        "MSFT": "https://cdn.example.com/msft.png",
    }

    manifest = PolygonBackend.build_finance_manifest(input_data)

    assert "AAPL" in manifest.tickers
    assert "MSFT" in manifest.tickers
    assert len(manifest.tickers) == 2


def test_build_finance_manifest_empty_dict():
    """Test that build_finance_manifest works with empty input."""
    manifest = PolygonBackend.build_finance_manifest({})

    assert isinstance(manifest, FinanceManifest)
    assert manifest.tickers == {}


def test_build_finance_manifest_invalid_url_logs_and_returns_empty(caplog):
    """Test that build_finance_manifest returns an empty manifest and logs validation error
    when the input contains an invalid URL.
    """
    input_data = {"AAPL": "not-a-valid-url"}

    caplog.set_level(logging.ERROR)

    manifest = PolygonBackend.build_finance_manifest(input_data)

    assert isinstance(manifest, FinanceManifest)
    assert manifest.tickers == {}

    assert any("Failed to build FinanceManifest" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_fetch_manifest_data_success(polygon: PolygonBackend, mocker):
    """Test that fetch_manifest_data returns SUCCESS and a valid FinanceManifest
    when the filemanager returns a valid result.
    """
    mock_manifest = FinanceManifest(tickers={"AAPL": "https://cdn.example.com/aapl.png"})

    mocker.patch.object(
        polygon.filemanager,
        "get_file",
        new_callable=AsyncMock,
        return_value=(GetManifestResultCode.SUCCESS, mock_manifest),
    )

    result_code, manifest = await polygon.fetch_manifest_data()

    assert result_code == GetManifestResultCode.SUCCESS
    assert isinstance(manifest, FinanceManifest)
    assert "AAPL" in manifest.tickers


@pytest.mark.asyncio
async def test_fetch_manifest_data_fail(polygon: PolygonBackend, mocker):
    """Test that fetch_manifest_data returns FAIL and None if filemanager fails to load the manifest."""
    mocker.patch.object(
        polygon.filemanager,
        "get_file",
        new_callable=AsyncMock,
        return_value=(GetManifestResultCode.FAIL, None),
    )

    result_code, manifest = await polygon.fetch_manifest_data()

    assert result_code == GetManifestResultCode.FAIL
    assert manifest is None


@pytest.mark.asyncio
async def test_build_and_upload_manifest_file_success(polygon: PolygonBackend, mocker):
    """Test that build_and_upload_manifest_file uploads the manifest successfully."""
    polygon_upload_mock = mocker.patch.object(
        polygon,
        "bulk_download_and_upload_ticker_images",
        return_value={"AAPL": "https://cdn.example.com/aapl.png"},
    )

    upload_content_mock = mocker.patch.object(
        polygon.gcs_uploader, "upload_content", return_value=MagicMock()
    )

    await polygon.build_and_upload_manifest_file()

    polygon_upload_mock.assert_awaited_once()
    upload_content_mock.assert_called_once()


@pytest.mark.asyncio
async def test_build_and_upload_manifest_file_upload_fails(
    polygon: PolygonBackend, mocker, caplog
):
    """Test that build_and_upload_manifest_file logs an error if manifest upload fails."""
    caplog.set_level("ERROR")

    mocker.patch.object(
        polygon,
        "bulk_download_and_upload_ticker_images",
        return_value={"AAPL": "https://cdn.example.com/aapl.png"},
    )

    upload_content_mock = mocker.patch.object(
        polygon.gcs_uploader, "upload_content", return_value=None
    )

    await polygon.build_and_upload_manifest_file()

    upload_content_mock.assert_called_once()
    assert "polygon manifest upload failed" in caplog.text
