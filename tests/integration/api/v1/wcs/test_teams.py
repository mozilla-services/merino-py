# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for `GET /api/v1/wcs/teams`."""

from fastapi.testclient import TestClient

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


def test_team_icons_are_svg_from_prod_logo_bucket(client: TestClient) -> None:
    """All team flags serve SVG from the hardcoded production GCS bucket."""
    body = client.get(_PATH).json()

    icons = [team["icon_url"] for team in body["teams"] if team["icon_url"] is not None]

    assert icons
    expected_prefix = "https://storage.googleapis.com/merino-images-prod/logos/nations/svg/"
    assert all(icon.startswith(expected_prefix) for icon in icons)
