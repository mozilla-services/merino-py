# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/teams`."""

import freezegun
import pytest
from fastapi.testclient import TestClient

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.main import app
from merino.providers.wcs import get_provider as get_wcs_provider
from merino.providers.wcs.provider import WcsProvider

_PATH = "/api/v1/wcs/teams"


def test_teams_endpoint_returns_correct_list_of_teams(client: TestClient) -> None:
    """Response is a well-formed teams envelope with 48 unique, valid team objects."""
    # NOTE: These asserts are subject to change. The shape of the source data could change.
    response = client.get(_PATH)
    assert response.status_code == 200

    body = response.json()
    assert "teams" in body
    assert isinstance(body["teams"], list)
    assert len(body["teams"]) == 48

    # assert all of the teams have the required keys.
    required_keys = {
        "key",
        "global_team_id",
        "name",
        "region",
        "colors",
        "icon_url",
        "group",
        "eliminated",
    }
    for team in body["teams"]:
        assert required_keys == set(team.keys())

    keys = [team["key"] for team in body["teams"]]
    # assert all "key" keys are of format "ENG" / "FRA".
    assert all(len(k) == 3 and k.isupper() for k in keys)

    # assert that france has 3 colours and strings start with a "#"
    fra = next(t for t in body["teams"] if t["key"] == "FRA")
    assert len(fra["colors"]) == 3
    assert all(c.startswith("#") for c in fra["colors"])
    assert fra["group"] == "Group I"


def test_success_sets_short_public_cache_control(client: TestClient) -> None:
    """Successful teams responses are publicly cacheable for the default TTL."""
    response = client.get(_PATH)
    assert response.status_code == 200
    ttl = settings.providers.wcs.default_cache_control_ttl
    assert (
        response.headers["cache-control"]
        == f"public, s-maxage={ttl}, max-age={ttl}, stale-while-revalidate={ttl}"
    )


@pytest.mark.restore_load_manifest
def test_team_icons_are_svg_from_configured_cdn(client: TestClient) -> None:
    """All team flags serve SVG through the configured image CDN host."""
    body = client.get(_PATH).json()

    icons = [team["icon_url"] for team in body["teams"] if team["icon_url"] is not None]

    assert icons
    expected_prefix = "https://test-cdn.mozilla.net/logos/nations/svg/"
    assert all(icon.startswith(expected_prefix) for icon in icons)


def test_open_circuit_breaker_returns_503(client: TestClient, mocker) -> None:
    """A Redis cache failure trips the breaker; subsequent requests return 503 + Retry-After."""
    with freezegun.freeze_time("2026-06-15T16:00:00Z") as freezer:
        sport = mocker.Mock()
        sport.get_all_teams = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
        sport.get_eliminated_team_keys = mocker.AsyncMock(return_value=set())
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
        sport.get_all_teams = mocker.AsyncMock(return_value={})
        client.get(_PATH)
