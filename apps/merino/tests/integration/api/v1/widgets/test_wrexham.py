# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/widgets/wrexham endpoints."""

import pytest
from fastapi.testclient import TestClient

from merino.providers.widgets.wrexham.provider import WrexhamProvider

MATCHES_URL = "/api/v1/widgets/wrexham/matches"
STANDINGS_URL = "/api/v1/widgets/wrexham/standings"

MATCH_FIELDS = {
    "id",
    "competition",
    "kickoff",
    "home_team",
    "away_team",
    "period",
    "status",
    "clock",
    "home_score",
    "away_score",
    "home_penalty_score",
    "away_penalty_score",
    "updated_at",
}


def test_matches_returns_the_contract_shape(client: TestClient) -> None:
    """Returns previous, current and upcoming groups with the contract's match fields."""
    response = client.get(MATCHES_URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"previous", "current", "upcoming"}

    live_match = body["current"][0]
    assert set(live_match) == MATCH_FIELDS
    assert set(live_match["competition"]) == {"id", "name"}
    assert set(live_match["home_team"]) == {"id", "name", "logo_url"}
    assert live_match["kickoff"].endswith("Z")
    assert live_match["updated_at"].endswith("Z")


def test_matches_defaults_to_five_previous_and_upcoming(client: TestClient) -> None:
    """Returns up to five previous and upcoming matches by default."""
    body = client.get(MATCHES_URL).json()

    assert len(body["previous"]) == 5
    assert len(body["upcoming"]) == 5


def test_matches_applies_the_limit(client: TestClient) -> None:
    """Applies `limit` to previous and upcoming matches."""
    body = client.get(MATCHES_URL, params={"limit": 2}).json()

    assert len(body["previous"]) == 2
    assert len(body["upcoming"]) == 2
    assert len(body["current"]) == 1


@pytest.mark.parametrize("limit", ["0", "9", "five"], ids=["too_small", "too_large", "not_int"])
def test_matches_rejects_an_invalid_limit(client: TestClient, limit: str) -> None:
    """Returns 400 for a `limit` outside the allowed range or that isn't a number."""
    response = client.get(MATCHES_URL, params={"limit": limit})

    assert response.status_code == 400


def test_standings_returns_the_contract_shape(client: TestClient) -> None:
    """Returns the Championship table with the contract's standing fields."""
    response = client.get(STANDINGS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["competition"] == {"id": 34, "name": "EFL Championship"}
    assert len(body["standings"]) == 24
    assert set(body["standings"][0]) == {
        "position",
        "team",
        "played",
        "goal_difference",
        "points",
    }


def test_matches_returns_empty_groups_when_mock_data_disabled(
    client: TestClient, wrexham_provider: WrexhamProvider
) -> None:
    """Returns 200 with empty match groups when mock data is disabled."""
    wrexham_provider.mock_data_enabled = False

    response = client.get(MATCHES_URL)

    assert response.status_code == 200
    assert response.json() == {"previous": [], "current": [], "upcoming": []}


def test_standings_returns_empty_table_when_mock_data_disabled(
    client: TestClient, wrexham_provider: WrexhamProvider
) -> None:
    """Returns 200 with an empty table when mock data is disabled."""
    wrexham_provider.mock_data_enabled = False

    response = client.get(STANDINGS_URL)

    assert response.status_code == 200
    assert response.json() == {
        "competition": {"id": 34, "name": "EFL Championship"},
        "standings": [],
    }
