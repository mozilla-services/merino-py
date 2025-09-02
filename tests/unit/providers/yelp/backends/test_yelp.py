# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Polygon backend module."""

from typing import cast
from unittest.mock import AsyncMock

import orjson
import pytest
from pytest import LogCaptureFixture
from httpx import AsyncClient, Response, Request
from pytest_mock import MockerFixture
from tests.types import FilterCaplogFixture

from merino.configs import settings
from merino.providers.suggest.yelp.backends.yelp import YelpBackend

URL_BUSINESS_SEARCH = settings.yelp.url_business_search


@pytest.fixture(name="yelp")
def fixture_yelp_backend(mocker: MockerFixture) -> YelpBackend:
    """Yelp Backend for testing."""
    return YelpBackend(
        api_key="api_key",
        http_client=mocker.AsyncMock(spec=AsyncClient),
        url_business_search=URL_BUSINESS_SEARCH,
        cache_ttl_sec=86400,
    )


@pytest.fixture(name="yelp_response")
def fixture_yelp_response() -> dict:
    """Yelp api response for testing."""
    return {
        "businesses": [
            {
                "id": "123",
                "alias": "mochazilla-toronto",
                "name": "MochaZilla. - Toronto",
                "image_url": "https://example.com/o.jpg",
                "is_closed": False,
                "url": "https://www.yelp.com/biz/mochazilla-toronto",
                "review_count": 989,
                "categories": [
                    {"alias": "breakfast_brunch", "title": "Breakfast & Brunch"},
                ],
                "rating": 4.8,
                "coordinates": {"latitude": 43.7195, "longitude": -79.3944},
                "transactions": ["restaurant_reservation"],
                "price": "$$",
                "location": {
                    "address1": "123 Firefox Avenue",
                    "address2": None,
                    "address3": "",
                    "city": "Toronto",
                    "zip_code": "M5V 1R9",
                    "country": "CA",
                    "state": "ON",
                    "display_address": ["123 Firefox Avenue", "Toronto, ON M5V 1R9", "Canada"],
                },
                "phone": "+12361238888",
                "display_phone": "+1 234-123-8888",
                "distance": 1153.068003234908,
                "business_hours": [
                    {
                        "open": [
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 0},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 1},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 2},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 3},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 4},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 5},
                            {"is_overnight": False, "start": "0700", "end": "1500", "day": 6},
                        ],
                        "hours_type": "REGULAR",
                        "is_open_now": False,
                    }
                ],
            }
        ],
    }


@pytest.fixture(name="yelp_processed_response")
def fixture_yelp_processed_response() -> dict:
    """Yelp processed response for testing."""
    return {
        "name": "MochaZilla. - Toronto",
        "url": "https://www.yelp.com/biz/mochazilla-toronto",
        "address": "123 Firefox Avenue",
        "rating": 4.8,
        "price": "$$",
        "review_count": 989,
        "business_hours": [
            {
                "open": [
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 0},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 1},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 2},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 3},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 4},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 5},
                    {"is_overnight": False, "start": "0700", "end": "1500", "day": 6},
                ],
                "hours_type": "REGULAR",
                "is_open_now": False,
            }
        ],
        "image_url": "https://firefox-settings-attachments.cdn.mozilla.net/main-workspace/quicksuggest-other/6f44101f-8385-471e-b2dd-2b2ed6624637.svg",
    }


@pytest.mark.asyncio
async def test_get_business_success(
    yelp: YelpBackend, yelp_response: dict, yelp_processed_response: dict
) -> None:
    """Test get_businesses method returns valid response."""
    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)

    base_url = "https://api.yelp.com/v3"
    location = "toronto"
    term = "breakfast &"
    endpoint = URL_BUSINESS_SEARCH.format(location=location, term=term, limit=1)

    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(yelp_response),
        request=Request(method="GET", url=f"{base_url}{endpoint}"),
    )

    expected = yelp_processed_response
    actual = await yelp.get_business(term, location)
    assert actual == expected


@pytest.mark.asyncio
async def test_get_business_bad_response(
    yelp: YelpBackend,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test get_businesses method returns a bad response."""
    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)

    base_url = "https://api.yelp.com/v3"
    location = "toronto"
    term = "breakfast &"
    endpoint = URL_BUSINESS_SEARCH.format(location=location, term=term, limit=1)

    client_mock.get.return_value = Response(
        status_code=200,
        content="{}",
        request=Request(method="GET", url=f"{base_url}{endpoint}"),
    )

    _ = await yelp.get_business(term, location)
    records = filter_caplog(caplog.records, "merino.providers.suggest.yelp.backends.yelp")

    assert len(records) == 2
    # First record should be cache miss
    assert records[0].message.startswith("Yelp cache miss, calling API:")
    # Second record should be the error
    assert records[1].message.startswith("Yelp business response json has incorrect shape")


@pytest.mark.asyncio
async def test_get_business_failure_for_http_500(
    yelp: YelpBackend,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Test get_businesses method raises a HTTPStatusError 500."""
    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)

    base_url = "https://api.yelp.com/v3"
    location = "toronto"
    term = "breakfast &"
    endpoint = URL_BUSINESS_SEARCH.format(location=location, term=term, limit=1)

    client_mock.get.return_value = Response(
        status_code=500,
        content=b"",
        request=Request(method="GET", url=f"{base_url}{endpoint}"),
    )

    _ = await yelp.get_business(term, location)
    records = filter_caplog(caplog.records, "merino.providers.suggest.yelp.backends.yelp")

    assert len(records) == 2
    # First record should be cache miss
    assert records[0].message.startswith("Yelp cache miss, calling API:")
    # Second record should be the HTTP error
    assert records[1].message.startswith("Yelp request error")
    assert "500 Internal Server Error" in records[1].message


@pytest.mark.asyncio
async def test_cache_key_generation(yelp: YelpBackend) -> None:
    """Test cache key generation method."""
    # Test the actual cache key generation method
    key1 = yelp.generate_cache_key("coffee", "toronto")
    key2 = yelp.generate_cache_key("pizza", "new york")

    # Keys should be consistent for same inputs
    key3 = yelp.generate_cache_key("coffee", "toronto")
    assert key1 == key3

    # Different inputs should generate different keys
    assert key1 != key2

    # Keys should have the expected prefix
    assert key1.startswith("YelpBackend:v1:business_search:")
    assert key2.startswith("YelpBackend:v1:business_search:")

    # Keys should be deterministic
    assert len(key1) > 30  # Should be a reasonable length


@pytest.mark.asyncio
async def test_get_from_cache_with_redis_cache(mocker: MockerFixture) -> None:
    """Test get_from_cache with Redis cache adapter."""
    # Mock Redis cache properly
    cache_mock = mocker.AsyncMock()
    cache_mock.get.return_value = orjson.dumps({"name": "Test Business"})

    yelp = YelpBackend(
        api_key="test_key",
        http_client=mocker.AsyncMock(spec=AsyncClient),
        url_business_search="test_url",
        cache_ttl_sec=3600,
        cache=cache_mock,
    )

    result = await yelp.get_from_cache("test-key")

    cache_mock.get.assert_called_once_with("test-key")
    assert result == {"name": "Test Business"}


@pytest.mark.asyncio
async def test_cache_store_error_handling(
    yelp: YelpBackend,
    yelp_response: dict,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test error handling when cache storage fails."""
    # Mock the actual cache.set to raise an error (not store_in_cache)
    cache_mock = mocker.AsyncMock()
    cache_mock.set.side_effect = Exception("Redis connection failed")
    yelp.cache = cache_mock

    # Mock successful API response
    client_mock: AsyncMock = cast(AsyncMock, yelp.http_client)
    client_mock.get.return_value = Response(
        status_code=200,
        content=orjson.dumps(yelp_response),
        request=Request(method="GET", url="http://test.com"),
    )

    location = "toronto"
    term = "coffee"

    # Should still return result even if cache store fails
    result = await yelp.get_business(term, location)
    assert result is not None

    # Should log the cache error
    assert "Yelp cache store error" in caplog.text or "cache store error" in caplog.text.lower()


@pytest.mark.asyncio
async def test_cache_key_case_insensitive(yelp: YelpBackend) -> None:
    """Test that cache keys are case insensitive."""
    key1 = yelp.generate_cache_key("Coffee", "Toronto")
    key2 = yelp.generate_cache_key("coffee", "toronto")
    key3 = yelp.generate_cache_key("COFFEE", "TORONTO")

    # All should generate the same key due to case normalization
    assert key1 == key2 == key3


@pytest.mark.asyncio
async def test_get_from_cache_decode_error(
    mocker: MockerFixture, caplog: LogCaptureFixture
) -> None:
    """Test error handling when cached data cannot be decoded."""
    cache_mock = mocker.AsyncMock()
    cache_mock.get.return_value = b"invalid json data"

    yelp = YelpBackend(
        api_key="test_key",
        http_client=mocker.AsyncMock(spec=AsyncClient),
        url_business_search="test_url",
        cache_ttl_sec=3600,
        cache=cache_mock,
    )

    result = await yelp.get_from_cache("test-key")
    assert result is None
    assert "cache decode error" in caplog.text.lower()
