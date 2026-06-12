# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/matches`."""

import freezegun
import pytest
from starlette.testclient import TestClient

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.main import app
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.wcs import get_provider as get_wcs_provider
from merino.providers.wcs.provider import WcsProvider
from tests.wcs.factories import build_provider, event as build_event


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


def test_success_sets_short_public_cache_control(client: TestClient) -> None:
    """Successful matches responses are publicly cacheable for the default TTL."""
    response = client.get(_PATH)
    assert response.status_code == 200
    ttl = settings.providers.wcs.default_cache_control_ttl
    assert (
        response.headers["cache-control"]
        == f"public, s-maxage={ttl}, max-age={ttl}, stale-while-revalidate={ttl}"
    )


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


def test_matches_per_bucket(client: TestClient) -> None:
    """Each of `previous`, `current`, `next` has at least one event sharing a status."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()
    assert len(body["previous"]) >= 1
    assert len(body["current"]) >= 1
    assert len(body["next"]) >= 1
    assert all(e["status"] == "Final" for e in body["previous"])
    assert all(e["status"] == "In Progress" for e in body["current"])
    assert all(e["status"] == "Scheduled" for e in body["next"])


def test_buckets_are_sorted_for_display(client: TestClient) -> None:
    """Results are newest-first while current and upcoming stay chronological."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()

    assert body["previous"] == sorted(body["previous"], key=lambda e: e["date"], reverse=True)
    assert body["current"] == sorted(body["current"], key=lambda e: e["date"])
    assert body["next"] == sorted(body["next"], key=lambda e: e["date"])


@freezegun.freeze_time("2026-06-15T12:00:00Z")
def test_same_day_scheduled_match_is_next_until_kickoff(client: TestClient) -> None:
    """A same-day scheduled match remains upcoming until kickoff."""
    app.dependency_overrides[get_wcs_provider] = lambda: build_provider(
        events=[
            build_event(
                90086908,
                0,
                19,
                ("MEX", "Mexico", 90000868),
                ("RSA", "South Africa", 90001083),
                GameStatus.Scheduled,
            )
        ]
    )

    body = client.get(_PATH, params={"date": _ANCHOR}).json()

    assert body["previous"] == []
    assert body["current"] == []
    assert [event["global_event_id"] for event in body["next"]] == [90086908]


@freezegun.freeze_time("2026-06-15T19:01:00Z")
def test_scheduled_match_is_current_during_post_kickoff_grace(client: TestClient) -> None:
    """A same-day scheduled match remains current shortly after kickoff."""
    app.dependency_overrides[get_wcs_provider] = lambda: build_provider(
        events=[
            build_event(
                90086908,
                0,
                19,
                ("MEX", "Mexico", 90000868),
                ("RSA", "South Africa", 90001083),
                GameStatus.Scheduled,
            )
        ]
    )

    body = client.get(_PATH, params={"date": _ANCHOR}).json()

    assert body["previous"] == []
    assert [event["global_event_id"] for event in body["current"]] == [90086908]
    assert body["next"] == []


@freezegun.freeze_time("2026-06-11T12:00:00Z")
def test_explicit_date_keeps_upcoming_match_next_until_kickoff(client: TestClient) -> None:
    """The date parameter anchors the window, not the match-state reference time."""
    app.dependency_overrides[get_wcs_provider] = lambda: build_provider(
        events=[
            build_event(
                90086908,
                -4,
                19,
                ("MEX", "Mexico", 90000868),
                ("RSA", "South Africa", 90001083),
                GameStatus.Scheduled,
            )
        ]
    )

    body = client.get(_PATH, params={"date": "2026-06-12"}).json()

    assert body["previous"] == []
    assert body["current"] == []
    assert [event["global_event_id"] for event in body["next"]] == [90086908]


def test_event_contract_required_fields_are_non_null(client: TestClient) -> None:
    """Event fields Mobile branches on are always present and non-null."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()
    events = body["previous"] + body["current"] + body["next"]

    assert events
    for event in events:
        assert event["date"] is not None
        assert event["global_event_id"] is not None
        assert event["status_type"] is not None
        assert event["stage"] is not None


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


def test_matches_returns_nullable_tbd_sides(client: TestClient) -> None:
    """Knockout placeholders serialize null team objects for Mobile."""
    app.dependency_overrides[get_wcs_provider] = lambda: build_provider(
        events=[
            build_event(
                90086997,
                20,
                20,
                ("TBD", "TBD", 0),
                ("TBD", "TBD", 0),
                GameStatus.Scheduled,
                original_date="2026-07-05T00:00:00",
                stage="Quarterfinals",
                round_id=1617,
                season_type=3,
            )
        ]
    )

    body = client.get(_PATH, params={"date": "2026-07-05"}).json()

    assert body["next"][0]["home_team"] is None
    assert body["next"][0]["away_team"] is None
    assert body["next"][0]["stage"] == "Quarterfinals"
    assert body["next"][0]["query"] == "Quarterfinals World Cup 2026"


def test_invalid_date_returns_400(client: TestClient) -> None:
    """Merino's validation handler in main.py converts FastAPI's 422 to 400."""
    response = client.get(_PATH, params={"date": "not-a-date"})
    assert response.status_code == 400


def test_open_circuit_breaker_returns_503(client: TestClient, mocker) -> None:
    """A Redis cache failure trips the breaker; subsequent requests return 503 + Retry-After."""
    with freezegun.freeze_time("2026-06-15T16:00:00Z") as freezer:
        sport = mocker.Mock()
        sport.get_events_by_date = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
        app.dependency_overrides[get_wcs_provider] = lambda: WcsProvider(sport=sport)

        # Trip the breaker
        with pytest.raises(CacheAdapterError):
            client.get(_PATH)

        response = client.get(_PATH)
        assert response.status_code == 503
        assert response.json() == {"detail": "WCS temporarily unavailable"}
        assert response.headers["retry-after"] == "5"
        # 503s are not cached, so a recovered backend is served immediately.
        assert "cache-control" not in response.headers

        freezer.tick(settings.providers.wcs.circuit_breaker_recover_timeout_sec + 1)
        sport.get_events_by_date = mocker.AsyncMock(return_value=[])
        client.get(_PATH)


def test_team_icons_pinned_to_prod_logo_bucket(client: TestClient) -> None:
    """Stage lacks a CDN host override, so icons hardcode the prod GCS bucket."""
    body = client.get(_PATH, params={"date": _ANCHOR}).json()
    events = body["previous"] + body["current"] + body["next"]

    assert events
    icons = [e["home_team"]["icon_url"] for e in events] + [
        e["away_team"]["icon_url"] for e in events
    ]
    expected_prefix = "https://storage.googleapis.com/merino-images-prod/logos/nations/svg/"
    assert all(icon and icon.startswith(expected_prefix) for icon in icons)
