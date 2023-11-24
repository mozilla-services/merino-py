"""Tests for the Upday Provider"""
from typing import Any

import pytest
from httpx import AsyncClient, Request, Response
from pytest_mock import MockerFixture

from merino.newtab import UpdayProvider
from merino.newtab.base import Recommendation
from merino.newtab.upday_provider import UpdayError


@pytest.fixture(name="test_username")
def fixture_username():
    """Test username"""
    return "test_user"


@pytest.fixture(name="http_mock")
def fixture_http_mock(mocker: MockerFixture) -> Any:
    """Mock HTTP client"""
    return mocker.AsyncMock(spec=AsyncClient)


@pytest.fixture(name="provider")
def fixture_upday_provider(http_mock: AsyncClient, test_username: str) -> UpdayProvider:
    """Upday Provider fixture"""
    return UpdayProvider(
        username=test_username, password="fake", http_client=http_mock
    )  # nosec


@pytest.fixture(name="upday_articles_response")
def fixture_upday_articles() -> dict[str, Any]:
    """Test response for Upday Articles"""
    return {
        "articles": [
            {
                "id": "random string id",
                "title": "Title 1",
                "url": "https://www.upday.com/de/Title_1",
                "deepLinks": {"upday": "https://www.upday.com/Title_1/another"},
                "source": "upday",
                "sourceDomain": "upday.com",
                "previewText": "This is one way to insert preview text.",
                "category": {
                    "id": "politics",
                    "subcategories": ["politics.miscellaneous"],
                    "specialCategories": ["topnews", "rendered", "mainstream"],
                },
                "streamType": "ctk",
                "nerTags": [],
                "imageUrl": "https://example.com",
                "contentType": "text",
                "logoUrl": {"lightMode": "https://logo.com"},
                "colorCode": "#3bace5",
                "partnerUrl": "https://partner.com/Title_1",
                "publishTime": "2023-11-14T20:22:00Z",
                "clusterId": "asdfghjkl",
            },
            {
                "id": "random string id",
                "title": "Title 2",
                "url": "https://www.upday.com/de/Title_2",
                "deepLinks": {"upday": "https://www.upday.com/Title_2/another"},
                "source": "upday",
                "sourceDomain": "upday.com",
                "previewText": "There should be more preview text for Title 2 here. "
                "Just inserting more breaking new text.",
                "category": {
                    "id": "cars_motors",
                    "subcategories": ["cars_motors.miscellaneous"],
                    "specialCategories": ["topnews", "rendered", "mainstream"],
                },
                "streamType": "ctk",
                "nerTags": [],
                "imageUrl": "https://example.com",
                "contentType": "text",
                "logoUrl": {"lightMode": "https://logo.com"},
                "colorCode": "#3bace5",
                "partnerUrl": "https://partner.com/Title_2",
                "publishTime": "2023-11-14T20:13:00Z",
                "clusterId": "asdfghjkl",
            },
        ]
    }


@pytest.mark.asyncio
async def test_get_upday_recommendations(
    provider: UpdayProvider,
    http_mock: Any,
    upday_articles_response: dict[str, Any],
) -> None:
    """Test that get_upday_recommendations return the correctly formatted articles."""
    auth_response: dict[str, Any] = {
        "access_token": "REALLY REALLY LONG CODE",
        "scope": "platform",
        "token_type": "Bearer",
        "expires_in": 86399,
    }

    http_mock.post.return_value = Response(
        status_code=200,
        json=auth_response,
        request=Request(method="POST", url="/v1/oauth/token"),
    )
    http_mock.get.return_value = Response(
        status_code=200,
        json=upday_articles_response,
        request=Request(method="GET", url="/v1/ntk/articles"),
    )

    expected_response: list[Recommendation] = [
        Recommendation(
            url="https://partner.com/Title_1",
            title="Title 1",
            excerpt="This is one way to insert preview text.",
            publisher="upday",
            image_url="https://example.com",
        ),
        Recommendation(
            url="https://partner.com/Title_2",
            title="Title 2",
            excerpt="There should be more preview text for Title 2 here. "
            "Just inserting more breaking new text.",
            publisher="upday",
            image_url="https://example.com",
        ),
    ]

    assert expected_response == await provider.get_upday_recommendations("pl", "pl")


@pytest.mark.asyncio
async def test_get_upday_failed_authentication_request(
    provider: UpdayProvider,
    http_mock: Any,
) -> None:
    """Test that an error is raised when we cannot get an authentication token
    from Upday.
    """
    http_mock.post.return_value = Response(
        status_code=400,
        json={},
        request=Request(method="POST", url="/v1/oauth/token"),
    )
    with pytest.raises(
        UpdayError, match="Could not get authentication token from Upday."
    ):
        await provider.get_upday_recommendations("pl", "pl")


@pytest.mark.asyncio
async def test_get_upday_failed_get_articles_request(
    provider: UpdayProvider,
    http_mock: Any,
) -> None:
    """Test that an error is raised when we cannot get articles from Upday."""
    auth_response: dict[str, Any] = {
        "access_token": "REALLY REALLY LONG CODE",
        "scope": "platform",
        "token_type": "Bearer",
        "expires_in": 86399,
    }

    http_mock.post.return_value = Response(
        status_code=200,
        json=auth_response,
        request=Request(method="POST", url="/v1/oauth/token"),
    )
    http_mock.get.return_value = Response(
        status_code=500,
        json={},
        request=Request(method="GET", url="/v1/ntk/articles"),
    )
    with pytest.raises(UpdayError, match="Could not get articles from Upday."):
        await provider.get_upday_recommendations("pl", "pl")


@pytest.mark.asyncio
async def test_shutdown(
    provider: UpdayProvider,
    http_mock: Any,
) -> None:
    """Test shutdown closes http client."""
    await provider.shutdown()
    assert http_mock.aclose.called_once()
