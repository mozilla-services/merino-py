# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/widgets/wrexham endpoints."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from merino.providers.widgets.wrexham.protocol import (
    Competition,
    Match,
    MatchStatus,
    Standing,
    Team,
)
from merino.providers.widgets.wrexham.provider import WrexhamProvider
from merino.providers.widgets.wrexham.store import WrexhamStore
from merino.web import api_v1_widgets

MATCHES_URL = "/api/v1/widgets/wrexham/matches"
STANDINGS_URL = "/api/v1/widgets/wrexham/standings"
CHAMPIONSHIP_ID = 34
FA_CUP_ID = 27
KICKOFF = datetime(2026, 11, 2, 15, tzinfo=UTC)

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


def _match(match_id: int, status: MatchStatus, kickoff: datetime) -> Match:
    """Build a Championship match for tests."""
    started = status in (MatchStatus.InProgress, MatchStatus.Final)
    team = Team(id=1, name="Team", logo_url="https://example.com/logo.png")
    return Match(
        id=match_id,
        competition=Competition(id=CHAMPIONSHIP_ID, name="EFL Championship"),
        kickoff=kickoff,
        home_team=team,
        away_team=team,
        period=None,
        status=status,
        clock="60" if status == MatchStatus.InProgress else None,
        home_score=1 if started else None,
        away_score=0 if started else None,
        home_penalty_score=None,
        away_penalty_score=None,
        updated_at=kickoff,
    )


def test_matches_returns_the_expected_shape(client: TestClient) -> None:
    """Returns previous, current and upcoming groups with the expected match fields."""
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


def test_standings_returns_the_expected_shape(client: TestClient) -> None:
    """Returns the Championship table with the expected standing fields."""
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


def _standing(position: int) -> Standing:
    """Build a table row for tests."""
    team = Team(id=position, name=f"Team {position}", logo_url="https://example.com/logo.png")
    return Standing(position=position, team=team, played=14, goal_difference=0, points=20)


def test_matches_sets_cache_control_header(client: TestClient) -> None:
    """Sets a Cache-Control header so Fastly can cache the response."""
    response = client.get(MATCHES_URL)

    assert response.headers["Cache-Control"] == "public, max-age=10, s-maxage=10"


def test_matches_returns_grouped_matches_from_redis(
    client: TestClient, wrexham_provider: WrexhamProvider, store: WrexhamStore
) -> None:
    """Returns stored matches grouped by status, with live data replacing fixture data."""
    wrexham_provider.mock_data_enabled = False
    asyncio.run(
        store.write_fixtures(
            CHAMPIONSHIP_ID,
            [
                _match(1, MatchStatus.Final, KICKOFF - timedelta(days=7)),
                _match(2, MatchStatus.Scheduled, KICKOFF),
                _match(3, MatchStatus.Scheduled, KICKOFF + timedelta(days=7)),
            ],
        )
    )
    asyncio.run(store.write_fixtures(FA_CUP_ID, []))
    asyncio.run(store.write_live_matches([_match(2, MatchStatus.InProgress, KICKOFF)]))

    response = client.get(MATCHES_URL)

    assert response.status_code == 200
    body = response.json()
    assert [match["id"] for match in body["previous"]] == [1]
    assert [match["id"] for match in body["current"]] == [2]
    assert [match["id"] for match in body["upcoming"]] == [3]
    assert body["current"][0]["status"] == "InProgress"
    assert response.headers["Cache-Control"] == "public, max-age=10, s-maxage=10"


def test_matches_returns_503_when_no_fixtures_are_stored(
    client: TestClient, wrexham_provider: WrexhamProvider
) -> None:
    """Returns the 503 error response, without caching, when no fixtures are stored."""
    wrexham_provider.mock_data_enabled = False

    response = client.get(MATCHES_URL)

    assert response.status_code == 503
    assert response.json() == {
        "statusCode": 503,
        "message": "Wrexham data is temporarily unavailable. Please try again later.",
    }
    assert "Cache-Control" not in response.headers


@pytest.mark.parametrize("path", ["/widgets/wrexham/matches", "/widgets/wrexham/standings"])
def test_endpoints_document_the_503_response(path: str) -> None:
    """Lists the 503 error response, with its fields, in the API docs."""
    docs = get_openapi(title="widgets", version="test", routes=api_v1_widgets.router.routes)

    responses = docs["paths"][path]["get"]["responses"]
    schema_ref = responses["503"]["content"]["application/json"]["schema"]["$ref"]
    schema = docs["components"]["schemas"][schema_ref.rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"statusCode", "message"}


def test_standings_sets_cache_control_header(client: TestClient) -> None:
    """Sets a Cache-Control header so Fastly can cache the response."""
    response = client.get(STANDINGS_URL)

    assert response.headers["Cache-Control"] == "public, max-age=60, s-maxage=60"


def test_standings_returns_the_stored_table_from_redis(
    client: TestClient, wrexham_provider: WrexhamProvider, store: WrexhamStore
) -> None:
    """Returns the stored table, ordered by position, with a Cache-Control header."""
    wrexham_provider.mock_data_enabled = False
    asyncio.run(store.write_standings([_standing(2), _standing(1)]))

    response = client.get(STANDINGS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["competition"] == {"id": 34, "name": "EFL Championship"}
    assert [row["position"] for row in body["standings"]] == [1, 2]
    assert response.headers["Cache-Control"] == "public, max-age=60, s-maxage=60"


def test_standings_returns_an_empty_stored_table(
    client: TestClient, wrexham_provider: WrexhamProvider, store: WrexhamStore
) -> None:
    """Returns 200 with an empty table when the stored table is empty."""
    wrexham_provider.mock_data_enabled = False
    asyncio.run(store.write_standings([]))

    response = client.get(STANDINGS_URL)

    assert response.status_code == 200
    assert response.json() == {
        "competition": {"id": 34, "name": "EFL Championship"},
        "standings": [],
    }


def test_standings_returns_503_when_no_standings_are_stored(
    client: TestClient, wrexham_provider: WrexhamProvider
) -> None:
    """Returns the 503 error response, without caching, when no standings are stored."""
    wrexham_provider.mock_data_enabled = False

    response = client.get(STANDINGS_URL)

    assert response.status_code == 503
    assert response.json() == {
        "statusCode": 503,
        "message": "Wrexham data is temporarily unavailable. Please try again later.",
    }
    assert "Cache-Control" not in response.headers
