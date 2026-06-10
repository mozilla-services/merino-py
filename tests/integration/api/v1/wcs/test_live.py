# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/live`."""

from collections.abc import Iterator

import freezegun
import pytest
from starlette.testclient import TestClient

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.main import app
from merino.providers.wcs import get_provider as get_wcs_provider
from merino.providers.wcs.provider import WcsProvider


_PATH = "/api/v1/wcs/live"


@pytest.fixture(autouse=True)
def _freeze_live_now() -> Iterator[None]:
    """Keep deterministic fixture events inside the live Redis query window."""
    with freezegun.freeze_time("2026-06-15T16:00:00Z"):
        yield


def test_returns_matches_envelope(client: TestClient) -> None:
    """Response is `{"matches": [...]}` with in-progress cached events."""
    response = client.get(_PATH)
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"matches"}
    assert isinstance(body["matches"], list)
    assert body["matches"]
    assert {e["status_type"] for e in body["matches"]} == {"live"}
    assert {event["status"] for event in body["matches"]} == {"In Progress"}


def test_success_sets_short_public_cache_control(client: TestClient) -> None:
    """Successful live responses are publicly cacheable for the default TTL."""
    response = client.get(_PATH)
    assert response.status_code == 200
    ttl = settings.providers.wcs.default_cache_control_ttl
    assert response.headers["cache-control"] == f"public, s-maxage={ttl}, max-age={ttl}"


def test_matches_sorted_ascending_by_date(client: TestClient) -> None:
    """Live matches come back ordered by event start time."""
    matches = client.get(_PATH).json()["matches"]
    assert matches == sorted(matches, key=lambda e: e["date"])


def test_event_contract_required_fields_are_non_null(client: TestClient) -> None:
    """Live endpoint mock events include the required Mobile branch fields."""
    matches = client.get(_PATH).json()["matches"]

    assert matches
    for event in matches:
        assert event["date"] is not None
        assert event["global_event_id"] is not None
        assert event["status_type"] is not None
        assert event["stage"] is not None


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


def test_open_circuit_breaker_returns_503(client: TestClient, mocker) -> None:
    """A Redis cache failure trips the breaker; subsequent requests return 503 + Retry-After."""
    with freezegun.freeze_time("2026-06-15T16:00:00Z") as freezer:
        sport = mocker.Mock()
        sport.get_events_by_date = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
        app.dependency_overrides[get_wcs_provider] = lambda: WcsProvider(
            sport=sport, live_data_enabled=True
        )

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
