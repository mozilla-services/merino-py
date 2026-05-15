# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/live`."""

from starlette.testclient import TestClient


_PATH = "/api/v1/wcs/live"


def test_returns_matches_envelope(client: TestClient) -> None:
    """Response is `{"matches": [...]}` with the mocked live-endpoint events."""
    response = client.get(_PATH)
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"matches"}
    assert isinstance(body["matches"], list)
    assert body["matches"]
    assert {e["status_type"] for e in body["matches"]} == {
        "live",
        "past",
        "scheduled",
        "unknown",
    }
    assert {"Awarded", "Canceled", "Postponed", "Suspended"}.issubset(
        {event["status"] for event in body["matches"]}
    )


def test_matches_sorted_ascending_by_date(client: TestClient) -> None:
    """Matches come back ordered by event start time."""
    matches = client.get(_PATH).json()["matches"]
    assert matches == sorted(matches, key=lambda e: e["date"])


def test_teams_filter(client: TestClient) -> None:
    """`teams` filter keeps only matches with that key on either side."""
    body = client.get(_PATH, params={"teams": "BRA"}).json()

    assert body["matches"]
    for event in body["matches"]:
        assert "BRA" in {event["home_team"]["key"], event["away_team"]["key"]}


def test_unknown_team_returns_empty_list(client: TestClient) -> None:
    """A `teams` value that matches nothing yields an empty list, not an error."""
    response = client.get(_PATH, params={"teams": "ZZZ"})
    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_team_icons_are_svg(client: TestClient) -> None:
    """Live match team flags serve SVG from the production GCS bucket."""
    matches = client.get(_PATH).json()["matches"]

    assert matches

    # pull out all home & away team icons
    icons = [
        team["icon_url"] for match in matches for team in (match["home_team"], match["away_team"])
    ]

    expected_prefix = "https://storage.googleapis.com/merino-images-prod/logos/nations/svg/"
    assert all(icon.startswith(expected_prefix) for icon in icons)
