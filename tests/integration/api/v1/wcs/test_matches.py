# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/matches`."""

from starlette.testclient import TestClient


_PATH = "/api/v1/wcs/matches"
# Pick an anchor inside the fake-data window so buckets are populated.
_ANCHOR = "2026-06-15"


def test_default_date_returns_three_buckets(client: TestClient) -> None:
    """A no-arg call returns the three bucket keys with list values."""
    response = client.get(_PATH)
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"previous", "current", "next"}
    assert isinstance(body["previous"], list)
    assert isinstance(body["current"], list)
    assert isinstance(body["next"], list)


def test_response_uses_alias_next(client: TestClient) -> None:
    """The JSON key must be `next`, not the Python `next_` field name."""
    body = client.get(_PATH).json()
    assert "next" in body
    assert "next_" not in body


def test_explicit_date_is_deterministic(client: TestClient) -> None:
    """Same `date` param yields byte-identical payloads."""
    a = client.get(_PATH, params={"date": _ANCHOR}).json()
    b = client.get(_PATH, params={"date": _ANCHOR}).json()
    assert a == b


def test_two_matches_per_bucket(client: TestClient) -> None:
    """Each of `previous`, `current`, `next` has exactly two events sharing a status."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()
    assert len(body["previous"]) == 2
    assert len(body["current"]) == 2
    assert len(body["next"]) == 2
    assert all(e["status"] == "Final" for e in body["previous"])
    assert all(e["status"] == "In Progress" for e in body["current"])
    assert all(e["status"] == "Scheduled" for e in body["next"])


def test_limit_clamps_each_bucket(client: TestClient) -> None:
    """`limit` caps each bucket independently."""
    body = client.get(_PATH, params={"date": _ANCHOR, "limit": 1}).json()
    assert len(body["previous"]) <= 1
    assert len(body["current"]) <= 1
    assert len(body["next"]) <= 1


def test_teams_filter(client: TestClient) -> None:
    """`teams` filter keeps only events with that key on either side."""
    body = client.get(_PATH, params={"date": _ANCHOR, "teams": "BRA"}).json()
    events = body["previous"] + body["current"] + body["next"]

    assert events
    for event in events:
        assert "BRA" in {event["home_team"]["key"], event["away_team"]["key"]}


def test_invalid_date_returns_400(client: TestClient) -> None:
    """Merino's validation handler in main.py converts FastAPI's 422 to 400."""
    response = client.get(_PATH, params={"date": "not-a-date"})
    assert response.status_code == 400


def test_team_icons_pinned_to_prod_logo_bucket(client: TestClient) -> None:
    """Stage lacks a CDN host override, so icons hardcode the prod GCS bucket."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()
    events = body["previous"] + body["current"] + body["next"]

    assert events
    icons = [e["home_team"]["icon_url"]["png"] for e in events] + [
        e["away_team"]["icon_url"]["png"] for e in events
    ]
    expected_prefix = "https://storage.googleapis.com/merino-images-prod/logos/nations/nations_"
    assert all(icon and icon.startswith(expected_prefix) for icon in icons)
