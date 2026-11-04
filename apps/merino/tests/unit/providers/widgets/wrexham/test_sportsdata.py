# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget SportsDataIO backend and converters."""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from freezegun import freeze_time
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.providers.widgets.wrexham.protocol import MatchPeriod, MatchStatus
from merino.providers.widgets.wrexham.sportsdata import (
    API_KEY_HEADER,
    CHAMPIONSHIP,
    WREXHAM_TEAM_ID,
    SportsDataBackend,
    SportsDataBackendError,
    SportsDataGame,
    to_match,
)
from merino.utils.logos import LogoCategory
from tests.types import FilterCaplogFixture

API_KEY = "test-key"
BASE_URL = "https://api.sportsdata.io/v4/soccer/scores/json/"
FALLBACK = HttpUrl("https://test-cdn.mozilla.net/logos/soccer/fallback.png")
CARDIFF = 90001461
WEST_HAM = 90000527
UNKNOWN_TEAM = 1


def game(**overrides: Any) -> dict[str, Any]:
    """Return a raw SportsDataIO game, as found in `dev/local_data/wrexham`."""
    return {
        "GameId": 116415,
        "DateTime": "2026-11-04T19:45:00",
        "Status": "Scheduled",
        "Period": "Regular",
        "Clock": None,
        "ClockExtra": None,
        "GlobalHomeTeamId": WREXHAM_TEAM_ID,
        "GlobalAwayTeamId": CARDIFF,
        "HomeTeamName": "Wrexham AFC",
        "AwayTeamName": "Cardiff City FC",
        "HomeTeamScore": None,
        "AwayTeamScore": None,
        "HomeTeamScorePenalty": None,
        "AwayTeamScorePenalty": None,
        "UpdatedUtc": "2026-11-04T02:09:52",
        "AwayTeamMoneyLine": -108,
    } | overrides


def standing(team_id: int, name: str, order: int, scope: str = "Total") -> dict[str, Any]:
    """Return a raw SportsDataIO standing row."""
    return {
        "GlobalTeamID": team_id,
        "Name": f"{name} FC",
        "ShortName": name,
        "Scope": scope,
        "Order": order,
        "Games": 12,
        "GoalsDifferential": 3 - order,
        "Points": 30 - order,
    }


def backend(handler: Any) -> SportsDataBackend:
    """Return a backend whose requests are served by `handler`."""
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return SportsDataBackend(http_client=client, api_key=API_KEY, fallback_logo_url=FALLBACK)


@pytest.mark.asyncio
async def test_fetch_schedule_keeps_wrexham_matches_from_all_rounds() -> None:
    """Return Wrexham matches only, earliest first, across rounds. Games with unknown teams
    and null round collections don't fail the response.
    """
    rounds = [
        {
            "SeasonType": 1,
            "Games": [
                game(GameId=2, DateTime="2026-11-10T15:00:00"),
                game(GameId=3, GlobalHomeTeamId=CARDIFF, GlobalAwayTeamId=WEST_HAM),
                game(GameId=4, GlobalAwayTeamId=None, AwayTeamName=None),
            ],
            "Standings": [],
        },
        {
            "SeasonType": 1,
            "Games": [game(GameId=1, DateTime="2026-11-01T15:00:00")],
            "Standings": [],
        },
        {"SeasonType": 3, "Games": None, "Standings": None},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/Schedule/34/2027")
        assert request.headers[API_KEY_HEADER] == API_KEY
        return httpx.Response(200, json=rounds)

    matches = await backend(handler).fetch_schedule(CHAMPIONSHIP, 2027)

    assert [match.id for match in matches] == [1, 2]
    assert matches[0].competition == CHAMPIONSHIP


@pytest.mark.asyncio
@freeze_time("2026-11-04T12:00:00Z")
async def test_fetch_live_matches_requests_today_in_utc(
    mocker: MockerFixture, make_manifest: Any
) -> None:
    """Request today's games and convert a not-yet-started Wrexham match."""
    mocker.patch(
        "merino.utils.logos.load_manifest",
        return_value=make_manifest((LogoCategory.Soccer, str(CARDIFF))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/GamesByDate/34/2026-11-04")
        return httpx.Response(200, json=[game()])

    [match] = await backend(handler).fetch_live_matches(CHAMPIONSHIP)

    assert match.kickoff == datetime(2026, 11, 4, 19, 45, tzinfo=UTC)
    assert match.updated_at.tzinfo == UTC
    assert match.status is MatchStatus.Scheduled
    assert (match.period, match.clock, match.home_score) == (None, None, None)
    assert str(match.away_team.logo_url).endswith(f"soccer_{CARDIFF}.png")
    assert match.home_team.logo_url == FALLBACK


@pytest.mark.asyncio
async def test_fetch_standings_uses_latest_regular_season_table() -> None:
    """Serve the overall table of the latest regular-season round that has one, by position."""
    rounds = [
        {"SeasonType": 1, "Games": [], "Standings": [standing(WEST_HAM, "Old", 1)]},
        {
            "SeasonType": 1,
            "Games": [],
            "Standings": [
                standing(CARDIFF, "Cardiff City", 2),
                standing(UNKNOWN_TEAM, "Nowhere", 1),
                standing(WEST_HAM, "West Ham", 1, scope="Home"),
            ],
        },
        {"SeasonType": 1, "Games": [], "Standings": []},
        # A play-off round is ignored even if it has a table.
        {"SeasonType": 3, "Games": [], "Standings": [standing(WEST_HAM, "Play-off", 1)]},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/Standings/34/2027")
        return httpx.Response(200, json=rounds)

    standings = await backend(handler).fetch_standings(CHAMPIONSHIP, 2027)

    assert [(row.position, row.team.name) for row in standings] == [
        (1, "Nowhere"),
        (2, "Cardiff City"),
    ]
    assert standings[0].team.logo_url == FALLBACK
    assert (standings[1].played, standings[1].goal_difference, standings[1].points) == (12, 1, 28)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("InProgress", MatchStatus.InProgress),
        ("Start Delay", MatchStatus.Delayed),
        ("Rain Delay", MatchStatus.Delayed),
        ("Awarded", MatchStatus.Final),
    ],
    ids=["contract", "start-delay", "rain-delay", "awarded"],
)
def test_to_match_maps_status(status: str, expected: MatchStatus) -> None:
    """Map SportsDataIO statuses to contract statuses."""
    match = to_match(SportsDataGame.model_validate(game(Status=status)), CHAMPIONSHIP, FALLBACK)

    assert match is not None
    assert match.status is expected


def test_to_match_skips_unsupported_status(
    caplog: LogCaptureFixture, filter_caplog: FilterCaplogFixture
) -> None:
    """Drop a game with a status outside the contract and log a warning."""
    caplog.set_level(logging.WARNING)

    raw = SportsDataGame.model_validate(game(Status="NotNecessary"))

    assert to_match(raw, CHAMPIONSHIP, FALLBACK) is None
    [record] = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.sportsdata")
    assert record.__dict__["status"] == "NotNecessary"


def test_to_match_live_and_shootout_fields() -> None:
    """Format stoppage time in the clock and keep penalty shootout scores."""
    raw = SportsDataGame.model_validate(
        game(
            Status="InProgress",
            Period="PenaltyShootout",
            Clock=90,
            ClockExtra=3,
            HomeTeamScore=1,
            AwayTeamScore=1,
            HomeTeamScorePenalty=4,
            AwayTeamScorePenalty=3,
        )
    )

    match = to_match(raw, CHAMPIONSHIP, FALLBACK)

    assert match is not None
    assert match.period is MatchPeriod.PenaltyShootout
    assert match.clock == "90+3"
    assert (match.home_penalty_score, match.away_penalty_score) == (4, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, json=[{"GameId": "not a game"}])],
    ids=["http-error", "invalid-payload"],
)
async def test_fetch_errors_raise_backend_error(response: httpx.Response) -> None:
    """Raise a backend error, without retrying, for failed or malformed responses."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    with pytest.raises(SportsDataBackendError):
        await backend(handler).fetch_live_matches(CHAMPIONSHIP)
    assert calls == 1
