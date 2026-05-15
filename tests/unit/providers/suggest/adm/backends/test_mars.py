# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the MARS backend module."""

import json
from collections import defaultdict
from typing import Any

import httpx
import moz_merino_ext.amp
import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.exceptions import BackendError
from merino.providers.suggest.adm.backends.mars import MarsBackend
from merino.providers.suggest.adm.backends.protocol import (
    FormFactor,
    SegmentType,
    SuggestionContent,
)
from merino.utils.icon_processor import IconProcessor
from tests.types import FilterCaplogFixture


@pytest.fixture(name="mock_icon_processor")
def fixture_mock_icon_processor(mocker: MockerFixture) -> IconProcessor:
    """Create a mock IconProcessor for testing."""
    mock_processor: IconProcessor = mocker.create_autospec(IconProcessor, instance=True)

    async def mock_process(url: str, fallback_url: str | None = None) -> str:
        return url

    mock_processor.process_icon_url.side_effect = mock_process  # type: ignore
    return mock_processor


@pytest.fixture(name="mars_backend")
def fixture_mars_backend(mock_icon_processor: IconProcessor, statsd_mock: Any) -> MarsBackend:
    """Create a MarsBackend object for test."""
    return MarsBackend(
        base_url="http://test-mars-api",
        icon_processor=mock_icon_processor,
        metrics_client=statsd_mock,
        connect_timeout=5.0,
        request_timeout=10.0,
    )


ICON_URL = "https://mars-cdn.mozilla.com/icons/01.png"


@pytest.fixture(name="suggestion_array_json")
def fixture_suggestion_array_json() -> str:
    """Return the inner suggestions array as JSON (what AmpIndexManager expects)."""
    return json.dumps(
        [
            {
                "id": 2,
                "advertiser": "Example.org",
                "click_url": "https://example.org/click/mozilla",
                "full_keywords": [
                    ["firefox accounts", 3],
                    ["mozilla firefox accounts", 4],
                ],
                "iab_category": "5 - Education",
                "icon": ICON_URL,
                "serp_categories": [],
                "impression_url": "https://example.org/impression/mozilla",
                "keywords": [
                    "firefox",
                    "firefox account",
                    "firefox accounts",
                    "mozilla",
                    "mozilla firefox",
                    "mozilla firefox account",
                    "mozilla firefox accounts",
                ],
                "title": "Mozilla Firefox Accounts",
                "url": "https://example.org/target/mozfirefoxaccounts",
            }
        ]
    )


@pytest.fixture(name="suggestion_json")
def fixture_suggestion_json(suggestion_array_json: str) -> str:
    """Return suggestion JSON as returned by the MARS API.

    MARS wraps the array in ``{"suggestions": [...]}``.
    """
    return json.dumps({"suggestions": json.loads(suggestion_array_json)})


@pytest.fixture(name="suggestion_response")
def fixture_suggestion_response(suggestion_json: str) -> httpx.Response:
    """Return a successful MARS suggestion response with ETag."""
    return httpx.Response(
        status_code=200,
        text=suggestion_json,
        headers={"ETag": '"etag-v1"', "Content-Type": "application/json"},
        request=httpx.Request(
            method="GET",
            url="http://test-mars-api/data?country=US&form_factor=desktop",
        ),
    )


# Default config has 1 country (US) x 1 form_factor (desktop) = 1 segment.
# Tests use this to keep mock setup predictable.
DEFAULT_SEGMENT = (FormFactor.DESKTOP.value,)
DEFAULT_IDX_ID = f"US/{DEFAULT_SEGMENT}"


def test_init_invalid_base_url(mock_icon_processor: IconProcessor, statsd_mock: Any) -> None:
    """Test that a ValueError is raised if initializing with an empty base_url."""
    with pytest.raises(ValueError, match="The MARS 'base_url' parameter is not specified"):
        MarsBackend(
            base_url="",
            icon_processor=mock_icon_processor,
            metrics_client=statsd_mock,
            connect_timeout=5.0,
            request_timeout=10.0,
        )


@pytest.mark.asyncio
async def test_fetch(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that the fetch method returns the proper suggestion content."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    suggestion_content: SuggestionContent = await mars_backend.fetch()

    assert suggestion_content.index_manager.has(DEFAULT_IDX_ID)
    assert suggestion_content.index_manager.stats(DEFAULT_IDX_ID) == {
        "keyword_index_size": 5,
        "suggestions_count": 1,
        "icons_count": 1,
        "advertisers_count": 1,
        "url_templates_count": 1,
    }


@pytest.mark.asyncio
async def test_fetch_skip(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that cached content is preserved when all segments return 304.

    Mirrors RS ``test_fetch_skip``: first fetch populates data and icons,
    second fetch with 304 responses skips processing entirely and preserves
    the cached ``suggestion_content`` (including icons).
    """
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    suggestion_content_1st: SuggestionContent = await mars_backend.fetch()
    assert suggestion_content_1st.index_manager.has(DEFAULT_IDX_ID)
    assert mars_backend.etags[DEFAULT_IDX_ID] == '"etag-v1"'
    assert ICON_URL in suggestion_content_1st.icons

    # Second fetch: server returns 304 for all segments.
    not_modified_response = httpx.Response(
        status_code=304,
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=not_modified_response,
    )

    suggestion_content_2nd: SuggestionContent = await mars_backend.fetch()

    # Index and icons should be preserved — early return with cached content.
    assert suggestion_content_2nd.index_manager.has(DEFAULT_IDX_ID)
    assert ICON_URL in suggestion_content_2nd.icons


@pytest.mark.asyncio
async def test_fetch_partial_update(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_json: str,
) -> None:
    """Test that a partial update (some 304, some 200) merges icons.

    Simulates 2 segments: US/desktop uses one icon URL, DE/desktop uses
    another. On second fetch, US returns 304 (unchanged) and DE returns 200
    with new data. Icons from both segments must be preserved.
    """
    de_icon_url = "https://mars-cdn.mozilla.com/icons/02.png"
    us_json = suggestion_json  # uses ICON_URL
    de_json = json.dumps(
        {
            "suggestions": [
                {
                    "id": 3,
                    "advertiser": "DE-Example.org",
                    "click_url": "https://de.example.org/click",
                    "full_keywords": [["berlin", 3]],
                    "iab_category": "5 - Education",
                    "icon": de_icon_url,
                    "serp_categories": [],
                    "impression_url": "https://de.example.org/impression",
                    "keywords": ["berlin"],
                    "title": "Berlin Guide",
                    "url": "https://de.example.org/target/berlin",
                }
            ]
        }
    )

    us_response = httpx.Response(
        status_code=200,
        text=us_json,
        headers={"ETag": '"etag-us-v1"', "Content-Type": "application/json"},
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    de_response = httpx.Response(
        status_code=200,
        text=de_json,
        headers={"ETag": '"etag-de-v1"', "Content-Type": "application/json"},
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )

    # Patch settings so fetch() iterates over US + DE.
    mocker.patch(
        "merino.providers.suggest.adm.backends.mars.settings.mars.countries",
        ["US", "DE"],
    )
    mocker.patch(
        "merino.providers.suggest.adm.backends.mars.settings.mars.form_factors",
        ["desktop"],
    )

    # First fetch: both segments return 200.
    mocker.patch.object(httpx.AsyncClient, "get", side_effect=[us_response, de_response])

    suggestion_content_1st = await mars_backend.fetch()

    de_idx_id = f"DE/{DEFAULT_SEGMENT}"
    assert suggestion_content_1st.index_manager.has(DEFAULT_IDX_ID)
    assert suggestion_content_1st.index_manager.has(de_idx_id)
    assert ICON_URL in suggestion_content_1st.icons
    assert de_icon_url in suggestion_content_1st.icons

    # Second fetch: US returns 304, DE returns 200 with new data.
    us_304 = httpx.Response(
        status_code=304,
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(httpx.AsyncClient, "get", side_effect=[us_304, de_response])

    suggestion_content_2nd = await mars_backend.fetch()

    # Both icons preserved: ICON_URL from cached US, de_icon_url from refreshed DE.
    assert ICON_URL in suggestion_content_2nd.icons
    assert de_icon_url in suggestion_content_2nd.icons


@pytest.mark.asyncio
async def test_fetch_with_index_build_fail(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test logging when building the index fails."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )
    mocker.patch.object(
        moz_merino_ext.amp.AmpIndexManager,
        "build",
        side_effect=Exception("Build Index Error"),
    )

    await mars_backend.fetch()

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.backends.mars")
    assert len(records) == 1
    assert records[0].__dict__["error message"] == "Build Index Error"


@pytest.mark.asyncio
async def test_fetch_http_error(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that MarsError is raised on HTTP failures."""
    error_response = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=error_response,
    )

    with pytest.raises(BackendError):
        await mars_backend.fetch()


@pytest.mark.asyncio
async def test_fetch_invalid_json(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that MarsError is raised when the response body is not valid JSON."""
    bad_response = httpx.Response(
        status_code=200,
        text="not json",
        headers={"Content-Type": "application/json"},
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=bad_response,
    )

    with pytest.raises(BackendError, match="Invalid JSON"):
        await mars_backend.fetch()


@pytest.mark.asyncio
async def test_fetch_missing_suggestions_key(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that MarsError is raised when the 'suggestions' key is missing."""
    bad_shape_response = httpx.Response(
        status_code=200,
        text=json.dumps({"data": []}),
        headers={"ETag": '"etag-v1"', "Content-Type": "application/json"},
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=bad_shape_response,
    )

    with pytest.raises(BackendError, match="missing 'suggestions' key"):
        await mars_backend.fetch()


@pytest.mark.asyncio
async def test_fetch_icons(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    mock_icon_processor: IconProcessor,
    suggestion_response: httpx.Response,
) -> None:
    """Test that IconProcessor is called for icons in use."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    suggestion_content = await mars_backend.fetch()

    # The suggestion has a full icon URL, so it should be in icons.
    assert ICON_URL in suggestion_content.icons
    mock_icon_processor.process_icon_url.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fetch_icon_processing_failure(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that icon processing failure falls back to the original URL."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    async def mock_process_fail(url: str, fallback_url: str | None = None) -> str:
        raise Exception("GCS upload failed")

    mars_backend.icon_processor.process_icon_url = mock_process_fail  # type: ignore[method-assign]

    suggestion_content = await mars_backend.fetch()

    # Icon should fall back to original URL.
    assert ICON_URL in suggestion_content.icons
    assert suggestion_content.icons[ICON_URL] == ICON_URL

    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.backends.mars")
    error_records = [r for r in records if r.levelname == "ERROR"]
    assert len(error_records) >= 1


@pytest.mark.asyncio
async def test_get_suggestions(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_array_json: str,
    suggestion_response: httpx.Response,
) -> None:
    """Test that get_suggestions returns the proper structure."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    segments = [("US", DEFAULT_SEGMENT, "desktop", DEFAULT_IDX_ID)]
    suggestions: defaultdict[str, dict[SegmentType, str]] = await mars_backend.get_suggestions(
        segments
    )

    assert "US" in suggestions
    assert list(suggestions["US"].keys()) == [DEFAULT_SEGMENT]
    # get_suggestion_data unwraps {"suggestions": [...]} and returns the array.
    assert json.loads(suggestions["US"][DEFAULT_SEGMENT]) == json.loads(suggestion_array_json)


@pytest.mark.asyncio
async def test_get_suggestion_data(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_array_json: str,
    suggestion_response: httpx.Response,
) -> None:
    """Test that get_suggestion_data extracts the suggestions array."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    result = await mars_backend.get_suggestion_data("US", "desktop", DEFAULT_IDX_ID)

    assert result is not None
    assert json.loads(result) == json.loads(suggestion_array_json)


@pytest.mark.asyncio
async def test_get_suggestion_data_backend_error(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that MarsError is raised on connection failures."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        side_effect=httpx.ConnectError("Connection refused"),
    )

    with pytest.raises(BackendError):
        await mars_backend.get_suggestion_data("US", "desktop", DEFAULT_IDX_ID)


def test_get_segment_invalid_form_factor(mars_backend: MarsBackend) -> None:
    """Test that get_segment raises KeyError for unknown form factors."""
    with pytest.raises(KeyError):
        mars_backend.get_segment("tablet")


@pytest.mark.asyncio
async def test_fetch_empty_suggestions(
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that empty suggestions preserve cached data and emit metric."""
    # First fetch populates the cache.
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )
    await mars_backend.fetch()
    assert mars_backend.suggestion_content.index_manager.has(DEFAULT_IDX_ID)

    # Second fetch: MARS returns 200 with empty suggestions.
    empty_response = httpx.Response(
        status_code=200,
        text=json.dumps({"suggestions": []}),
        headers={"ETag": '"etag-v2"', "Content-Type": "application/json"},
        request=httpx.Request(
            method="GET",
            url="http://test-mars-api/data?country=US&form_factor=desktop",
        ),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=empty_response,
    )

    suggestion_content = await mars_backend.fetch()

    # Cached index should be preserved (not wiped).
    assert suggestion_content.index_manager.has(DEFAULT_IDX_ID)

    # Warning should be logged.
    records = filter_caplog(caplog.records, "merino.providers.suggest.adm.backends.mars")
    warning_records = [r for r in records if r.levelname == "WARNING"]
    assert any("empty suggestions" in r.message for r in warning_records)

    # Empty response metric should be incremented.
    mars_backend.metrics_client.increment.assert_any_call(  # type: ignore[attr-defined]
        "mars.fetch",
        tags={"country": "US", "form_factor": "desktop", "status": "empty_response"},
    )


@pytest.mark.asyncio
async def test_fetch_metrics_on_success(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that mars.fetch with status=success is incremented on 200 with data."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    await mars_backend.fetch()

    mars_backend.metrics_client.increment.assert_any_call(  # type: ignore[attr-defined]
        "mars.fetch",
        tags={"country": "US", "form_factor": "desktop", "status": "success"},
    )


@pytest.mark.asyncio
async def test_fetch_metrics_on_304(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that mars.fetch with status=not_modified is incremented on 304."""
    not_modified_response = httpx.Response(
        status_code=304,
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=not_modified_response,
    )

    await mars_backend.fetch()

    mars_backend.metrics_client.increment.assert_any_call(  # type: ignore[attr-defined]
        "mars.fetch",
        tags={"country": "US", "form_factor": "desktop", "status": "not_modified"},
    )


@pytest.mark.asyncio
async def test_fetch_metrics_on_error(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
) -> None:
    """Test that mars.fetch with status=error is incremented on HTTP errors."""
    error_response = httpx.Response(
        status_code=500,
        text="Internal Server Error",
        request=httpx.Request(method="GET", url="http://test-mars-api/data"),
    )
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=error_response,
    )

    with pytest.raises(BackendError):
        await mars_backend.fetch()

    mars_backend.metrics_client.increment.assert_any_call(  # type: ignore[attr-defined]
        "mars.fetch",
        tags={"country": "US", "form_factor": "desktop", "status": "error"},
    )


@pytest.mark.asyncio
async def test_last_new_data_at_set_on_success(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that last_new_data_at is set after a successful 200 with data."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    assert mars_backend.last_new_data_at == 0.0

    await mars_backend.fetch()

    assert mars_backend.last_new_data_at > 0


@pytest.mark.asyncio
async def test_fetch_response_size_metric(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_json: str,
    suggestion_response: httpx.Response,
) -> None:
    """Test that mars.fetch.response_size_bytes gauge is emitted on 200."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    await mars_backend.fetch()

    mars_backend.metrics_client.gauge.assert_any_call(  # type: ignore[attr-defined]
        "mars.fetch.response_size_bytes",
        value=len(suggestion_json.encode()),
        tags={"country": "US", "form_factor": "desktop"},
    )


@pytest.mark.asyncio
async def test_index_metrics_emitted_after_build(
    mocker: MockerFixture,
    mars_backend: MarsBackend,
    suggestion_response: httpx.Response,
) -> None:
    """Test that amp.index.* gauges are emitted after a successful index build."""
    mocker.patch.object(
        httpx.AsyncClient,
        "get",
        return_value=suggestion_response,
    )

    await mars_backend.fetch()

    gauge_calls = mars_backend.metrics_client.gauge.call_args_list  # type: ignore[attr-defined]
    index_calls = {c[0][0]: c[1] for c in gauge_calls if c[0][0].startswith("amp.index.")}

    assert "amp.index.suggestions_count" in index_calls
    assert index_calls["amp.index.suggestions_count"]["value"] == 1
    assert index_calls["amp.index.suggestions_count"]["tags"] == {"index": "US/desktop"}

    assert "amp.index.keyword_index_size" in index_calls
    assert index_calls["amp.index.keyword_index_size"]["value"] == 5
