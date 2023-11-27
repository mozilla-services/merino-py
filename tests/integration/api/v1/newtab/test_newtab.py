"""Integration tests for the New Tab API."""
from collections import namedtuple
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino.main import app
from merino.newtab import get_upday_provider
from merino.newtab.base import Recommendation


@pytest.fixture(name="upday_mock")
def fixture_set_up_upday(mocker: MockerFixture) -> Any:
    """Mock Fixture for Upday provider."""
    return mocker.AsyncMock()


@pytest.fixture(autouse=True)
def fixture_inject_upday(upday_mock: Any):
    """Fixture to inject Upday into the app. Simulates a start up."""
    app.dependency_overrides[get_upday_provider] = lambda: upday_mock


Scenario = namedtuple("Scenario", ["upday_side_effect", "expected_response"])

SCENARIOS: dict[str, Scenario] = {
    "Case-I: Return empty Upday response": Scenario(
        upday_side_effect=[], expected_response={"data": []}
    ),
    "Case-II: Return Upday response": Scenario(
        upday_side_effect=[
            Recommendation(
                title="Title",
                url="https://localhost/",
                image_url="https://localhost/",
                excerpt="This is the excerpt",
                publisher="upday",
            )
        ],
        expected_response={
            "data": [
                {
                    "__typename": "Recommendation",
                    "url": "https://localhost/",
                    "title": "Title",
                    "excerpt": "This is the excerpt",
                    "publisher": "upday",
                    "imageUrl": "https://localhost/",
                    "titleId": None,
                    "timeToRead": None,
                }
            ]
        },
    ),
}


@pytest.mark.parametrize(
    argnames=["upday_side_effect", "expected_response"],
    argvalues=SCENARIOS.values(),
    ids=SCENARIOS.keys(),
)
@pytest.mark.asyncio
async def test_newtab_upday(
    client: TestClient,
    upday_mock: Any,
    upday_side_effect: Any,
    expected_response: dict[str, Any],
) -> None:
    """Test that the newtab endpoint returns results as expected."""
    upday_mock.get_upday_recommendations.side_effect = [upday_side_effect]
    response = client.get("/api/v1/newtab?locale=nl&language=nl")
    assert response.status_code == 200

    result = response.json()
    assert result == expected_response

    await upday_mock.get_upday_recommendations.called_once_with("nl", "nl")


def test_newtab_upday_no_provider(client: TestClient) -> None:
    """Test the path where provider is not initialized."""
    app.dependency_overrides[get_upday_provider] = lambda: None
    response = client.get("/api/v1/newtab?locale=nl&language=nl")
    assert response.status_code == 200

    result = response.json()
    assert result == {"data": []}
