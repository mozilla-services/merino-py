# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the WCS matches provider."""

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.providers import wcs as wcs_module
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.wcs.fake_live_data import build_live_events
from merino.providers.wcs.provider import WcsProvider, _WINDOW
from merino.providers.wcs.protocol import LiveMatchesResponse, TeamInfo, TeamsResponse
from tests.wcs.factories import ANCHOR, build_provider, build_teams, event as build_event

_LIVE_EVENT_COUNT = len(build_live_events(ANCHOR))


def test_cache_uses_wcs_redis_settings(mocker) -> None:
    """The WCS API provider reads from the dedicated WCS Redis connection."""
    adapter = object()
    create_redis_clients = mocker.patch.object(
        wcs_module,
        "create_redis_clients",
        return_value=("primary", "replica"),
    )
    redis_adapter = mocker.patch.object(wcs_module, "RedisAdapter", return_value=adapter)

    assert wcs_module._cache() is adapter
    create_redis_clients.assert_called_once_with(
        settings.redis.wcs_server,
        settings.redis.wcs_replica,
        settings.redis.max_connections,
        settings.redis.socket_connect_timeout_sec,
        settings.redis.socket_timeout_sec,
    )
    redis_adapter.assert_called_once_with("primary", "replica")


def _dates(events: list[Any]) -> list[date]:
    return [datetime.fromisoformat(e.date).date() for e in events]


@pytest.mark.asyncio
async def test_buckets_split_by_date() -> None:
    """Each bucket holds events on the correct side of `target_date`."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    assert all(d < ANCHOR for d in _dates(response.previous))
    assert all(d == ANCHOR for d in _dates(response.current))
    assert all(d > ANCHOR for d in _dates(response.next_))


@pytest.mark.asyncio
async def test_window_excludes_outside_range() -> None:
    """No event lands more than WINDOW days from the anchor."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    for event in response.previous + response.current + response.next_:
        delta = abs((datetime.fromisoformat(event.date).date() - ANCHOR).days)
        assert delta <= _WINDOW.days


@pytest.mark.asyncio
async def test_buckets_sorted_ascending_by_date() -> None:
    """Each bucket is sorted by event date ascending."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    for bucket in (response.previous, response.current, response.next_):
        assert bucket == sorted(bucket, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_limit_keeps_closest_to_target_date() -> None:
    """`previous` keeps the most-recent N, `next` keeps the soonest N."""
    provider = build_provider()
    full = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    limited = await provider.get_matches(ANCHOR, limit=1, team_keys=None)

    assert len(limited.previous) <= 1
    assert len(limited.current) <= 1
    assert len(limited.next_) <= 1
    if full.previous and limited.previous:
        assert limited.previous[-1].date == full.previous[-1].date
    if full.next_ and limited.next_:
        assert limited.next_[0].date == full.next_[0].date


@pytest.mark.asyncio
async def test_teams_filter_matches_either_side() -> None:
    """Filter retains events where either home or away `key` is in the set."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=frozenset({"BRA"}))
    events = response.previous + response.current + response.next_

    assert events
    for event in events:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_response_is_deterministic_for_same_anchor() -> None:
    """Two calls with the same anchor produce identical payloads."""
    provider = build_provider()
    a = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    b = await provider.get_matches(ANCHOR, limit=None, team_keys=None)

    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_six_records_two_per_status_type() -> None:
    """The stub set has at least two past, two live, and two scheduled matches
    assuming a window >= 7 days.
    """
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    assert len(response.previous) >= 2
    assert len(response.current) >= 2
    assert len(response.next_) >= 2
    assert all(e.status_type == "past" for e in response.previous)
    assert all(e.status_type == "live" for e in response.current)
    assert all(e.status_type == "scheduled" for e in response.next_)


@pytest.mark.asyncio
async def test_public_sport_identifier_is_soccer() -> None:
    """WCS responses expose the stable widget sport value, not the internal league key."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)
    events = response.previous + response.current + response.next_

    assert events
    assert {event.sport for event in events} == {"soccer"}


@pytest.mark.asyncio
async def test_matches_include_tbd_placeholder_teams() -> None:
    """The matches endpoint can return scheduled bracket placeholders."""
    placeholder = build_event(
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

    response = await build_provider(events=[placeholder]).get_matches(
        ANCHOR + timedelta(days=20),
        limit=None,
        team_keys=None,
    )

    assert len(response.current) == 1
    event = response.current[0]
    assert event.home_team.name == "TBD"
    assert event.home_team.global_team_id == 0
    assert event.home_team.icon_url is None
    assert event.away_team.name == "TBD"
    assert event.away_team.global_team_id == 0
    assert event.away_team.icon_url is None
    assert event.stage == "Quarterfinals"
    assert event.query == "World Cup 2026 TBD vs TBD 05 July 2026"


@pytest.mark.asyncio
async def test_match_team_colors_are_normalized_to_hex() -> None:
    """Cached event team color names are replaced with WCS hex colors."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)
    event = next(event for event in response.previous if event.home_team.key == "BRA")

    assert event.home_team.colors == ["#009C3B", "#FFDF00", "#002776"]
    assert event.away_team.colors == ["#74ACDF", "#FFFFFF", "#F6B40E"]


@pytest.mark.asyncio
async def test_extra_and_penalty_populated_on_one_finalized_match() -> None:
    """Exactly one finalized match exposes extra-time and penalty-shootout values."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    finalized_with_extras = [
        e for e in response.previous if e.home_extra is not None and e.home_penalty is not None
    ]
    assert len(finalized_with_extras) == 1
    event = finalized_with_extras[0]
    assert event.away_extra is not None
    assert event.away_penalty is not None


@pytest.mark.asyncio
async def test_live_extra_time_match_shows_clock_in_extra_play() -> None:
    """A live match in extra time renders its clock in '90+x' form."""
    response = await build_provider().get_matches(ANCHOR, limit=None, team_keys=None)

    in_extra = [e for e in response.current if e.period == "ET"]
    assert len(in_extra) == 1
    assert in_extra[0].clock.startswith("90+")


@pytest.mark.asyncio
async def test_live_returns_expanded_fake_events() -> None:
    """`get_live_matches` returns the expanded fake live-endpoint event set."""
    response = await build_provider(events=[]).get_live_matches(team_keys=None)

    assert len(response.matches) == _LIVE_EVENT_COUNT
    assert Counter(e.status_type for e in response.matches) == Counter(
        {
            "past": 5,
            "live": 11,
            "scheduled": 3,
            "unknown": 1,
        }
    )
    assert {"Awarded", "Canceled", "Postponed", "Suspended"}.issubset(
        {event.status for event in response.matches}
    )


@pytest.mark.asyncio
async def test_live_matches_sorted_ascending_by_date() -> None:
    """Live events are sorted ascending by `date`."""
    matches: LiveMatchesResponse = await build_provider().get_live_matches(team_keys=None)
    assert matches.matches == sorted(matches.matches, key=lambda e: e.date)


@pytest.mark.asyncio
async def test_live_teams_filter_matches_either_side() -> None:
    """Filter retains live events where either side plays for the listed team."""
    response = await build_provider().get_live_matches(team_keys=frozenset({"BRA"}))

    assert response.matches
    for event in response.matches:
        assert "BRA" in {event.home_team.key, event.away_team.key}


@pytest.mark.asyncio
async def test_live_unknown_team_returns_empty() -> None:
    """No match for the filter yields an empty list, not an error."""
    response = await build_provider().get_live_matches(team_keys=frozenset({"ZZZ"}))
    assert response.matches == []


@pytest.mark.asyncio
async def test_live_is_deterministic_within_same_utc_day() -> None:
    """Two calls in the same UTC day produce identical payloads."""
    provider = build_provider(events=[])
    a = await provider.get_live_matches(team_keys=None)
    b = await provider.get_live_matches(team_keys=None)
    assert a.model_dump() == b.model_dump()


@pytest.mark.asyncio
async def test_get_teams_count() -> None:
    """The cache-backed tournament roster has exactly 48 teams, all TeamInfo instances."""
    response = await build_provider().get_teams()
    assert len(response.teams) == 48
    assert isinstance(response, TeamsResponse)
    assert all(isinstance(team, TeamInfo) for team in response.teams)
    assert all(team.group for team in response.teams)


@pytest.mark.asyncio
async def test_teams_are_enriched_from_roster_metadata() -> None:
    """Cached SportsData teams are filtered, ordered, and enriched from the tournament roster."""
    teams = build_teams()
    non_roster_team = teams[0].model_copy(
        update={
            "key": "ITA",
            "id": 90000950,
            "name": "Italy",
            "country": None,
            "colors": ["Blue", "White"],
        }
    )

    response = await build_provider(teams=[non_roster_team, *reversed(teams)]).get_teams()

    assert len(response.teams) == 48
    assert [team.key for team in response.teams] == [team.key for team in build_teams()]
    assert "ITA" not in {team.key for team in response.teams}
    england = response.teams[0]
    assert england.key == "ENG"
    assert england.region == "ENG"
    assert england.group == "Group L"
    assert all(color.startswith("#") for color in england.colors)


@pytest.mark.asyncio
async def test_get_teams_uses_cached_eliminated_keys_without_calendar_scan(mocker) -> None:
    """The teams endpoint reads materialized eliminated keys instead of all events."""
    teams = build_teams()
    sport = mocker.Mock()
    sport.get_all_teams = mocker.AsyncMock(return_value={team.id: team for team in teams})
    sport.get_eliminated_team_keys = mocker.AsyncMock(return_value={teams[0].key})
    sport.get_events_by_date = mocker.AsyncMock()
    provider = WcsProvider(sport=sport)

    response = await provider.get_teams()

    eliminated_by_key = {team.key: team.eliminated for team in response.teams}
    assert eliminated_by_key[teams[0].key] is True
    sport.get_eliminated_team_keys.assert_awaited_once()
    sport.get_events_by_date.assert_not_called()


@pytest.mark.asyncio
async def test_group_stage_elimination_waits_for_full_round_of_32() -> None:
    """Group-stage teams stay active until all Round of 32 participants are populated."""
    teams = build_teams()
    partial_knockout_events = [
        build_event(
            9000 + index,
            14,
            index % 24,
            (teams[index * 2].key, teams[index * 2].name, teams[index * 2].id),
            (teams[(index * 2) + 1].key, teams[(index * 2) + 1].name, teams[(index * 2) + 1].id),
            GameStatus.Scheduled,
            round_id=1616,
            season_type=3,
        )
        for index in range(15)
    ]

    response = await build_provider(events=partial_knockout_events).get_teams()

    assert not any(team.eliminated for team in response.teams)


@pytest.mark.asyncio
async def test_group_stage_non_advancers_are_eliminated_after_round_of_32_populates() -> None:
    """Roster teams missing from the populated Round of 32 are eliminated."""
    teams = build_teams()
    round_of_32_events = [
        build_event(
            9100 + index,
            14,
            index % 24,
            (teams[index * 2].key, teams[index * 2].name, teams[index * 2].id),
            (teams[(index * 2) + 1].key, teams[(index * 2) + 1].name, teams[(index * 2) + 1].id),
            GameStatus.Scheduled,
            round_id=1616,
            season_type=3,
        )
        for index in range(16)
    ]

    response = await build_provider(events=round_of_32_events).get_teams()
    eliminated_by_key = {team.key: team.eliminated for team in response.teams}

    assert not any(eliminated_by_key[team.key] for team in teams[:32])
    assert all(eliminated_by_key[team.key] for team in teams[32:])


@pytest.mark.asyncio
async def test_knockout_loser_is_eliminated_from_winner_field() -> None:
    """A completed knockout game with HomeTeam as Winner eliminates the away side."""
    home, away = build_teams()[:2]
    knockout_event = build_event(
        9200,
        20,
        18,
        (home.key, home.name, home.id),
        (away.key, away.name, away.id),
        GameStatus.Final,
        home_score=2,
        away_score=1,
        round_id=1617,
        season_type=3,
        winner="HomeTeam",
        is_closed=True,
    )

    response = await build_provider(events=[knockout_event]).get_teams()
    eliminated_by_key = {team.key: team.eliminated for team in response.teams}

    assert eliminated_by_key[home.key] is False
    assert eliminated_by_key[away.key] is True


@pytest.mark.asyncio
async def test_knockout_home_team_is_eliminated_from_away_winner_field() -> None:
    """A completed knockout game with AwayTeam as Winner eliminates the home side."""
    home, away = build_teams()[:2]
    knockout_event = build_event(
        9201,
        20,
        18,
        (home.key, home.name, home.id),
        (away.key, away.name, away.id),
        GameStatus.Final,
        round_id=1617,
        season_type=3,
        winner="AwayTeam",
        is_closed=True,
    )

    response = await build_provider(events=[knockout_event]).get_teams()
    eliminated_by_key = {team.key: team.eliminated for team in response.teams}

    assert eliminated_by_key[home.key] is True
    assert eliminated_by_key[away.key] is False


@pytest.mark.asyncio
async def test_knockout_loser_is_not_inferred_from_penalties_without_winner() -> None:
    """A completed knockout game without `Winner` does not infer elimination from scores."""
    home, away = build_teams()[:2]
    knockout_event = build_event(
        9202,
        20,
        18,
        (home.key, home.name, home.id),
        (away.key, away.name, away.id),
        GameStatus.Final,
        home_score=1,
        away_score=1,
        home_penalty=4,
        away_penalty=5,
        round_id=1617,
        season_type=3,
        is_closed=True,
    )

    response = await build_provider(events=[knockout_event]).get_teams()
    eliminated_by_key = {team.key: team.eliminated for team in response.teams}

    assert eliminated_by_key[home.key] is False
    assert eliminated_by_key[away.key] is False


@pytest.mark.asyncio
async def test_scheduled_knockout_path_keeps_team_active() -> None:
    """A later scheduled knockout event overrides group-stage non-advancer elimination."""
    teams = build_teams()
    round_of_32_events = [
        build_event(
            9300 + index,
            14,
            index % 24,
            (teams[index * 2].key, teams[index * 2].name, teams[index * 2].id),
            (teams[(index * 2) + 1].key, teams[(index * 2) + 1].name, teams[(index * 2) + 1].id),
            GameStatus.Scheduled,
            round_id=1616,
            season_type=3,
        )
        for index in range(16)
    ]
    later_advancer = teams[40]
    later_knockout_event = build_event(
        9400,
        20,
        18,
        (later_advancer.key, later_advancer.name, later_advancer.id),
        (teams[41].key, teams[41].name, teams[41].id),
        GameStatus.Scheduled,
        round_id=1617,
        season_type=3,
    )

    response = await build_provider(events=[*round_of_32_events, later_knockout_event]).get_teams()
    eliminated_by_key = {team.key: team.eliminated for team in response.teams}

    assert eliminated_by_key[later_advancer.key] is False


@pytest.mark.asyncio
async def test_empty_cache_returns_empty_payloads() -> None:
    """An empty WCS event cache returns empty matches while cached teams are served."""
    provider = build_provider(events=[])

    matches = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    assert matches.model_dump(by_alias=True) == {
        "previous": [],
        "current": [],
        "next": [],
    }
    assert len((await provider.get_live_matches(team_keys=None)).matches) == _LIVE_EVENT_COUNT
    assert len((await provider.get_teams()).teams) == 48


@pytest.mark.asyncio
async def test_empty_team_cache_returns_empty_teams() -> None:
    """An empty WCS team cache returns an empty teams envelope."""
    assert (await build_provider(teams=[]).get_teams()).teams == []


@pytest.mark.asyncio
async def test_cache_error_returns_empty_payloads(mocker) -> None:
    """A transient WCS cache read failure returns empty cache-backed envelopes."""
    sport = mocker.Mock()
    sport.get_events_by_date = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
    sport.get_all_teams = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
    sport.get_eliminated_team_keys = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
    metrics_client = mocker.Mock()
    provider = WcsProvider(sport=sport, metrics_client=metrics_client)

    matches = await provider.get_matches(ANCHOR, limit=None, team_keys=None)
    assert matches.model_dump(by_alias=True) == {
        "previous": [],
        "current": [],
        "next": [],
    }
    assert len((await provider.get_live_matches(team_keys=None)).matches) == _LIVE_EVENT_COUNT
    assert (await provider.get_teams()).teams == []
    metrics_client.increment.assert_any_call("wcs.cache_error", tags={"endpoint": "matches"})
    metrics_client.increment.assert_any_call("wcs.cache_error", tags={"endpoint": "teams"})


@pytest.mark.asyncio
async def test_team_elimination_cache_error_leaves_teams_uneliminated(mocker) -> None:
    """A WCS elimination-cache error does not hide cache-backed team rows."""
    sport = mocker.Mock()
    sport.get_all_teams = mocker.AsyncMock(return_value={team.id: team for team in build_teams()})
    sport.get_eliminated_team_keys = mocker.AsyncMock(side_effect=CacheAdapterError("redis down"))
    metrics_client = mocker.Mock()
    provider = WcsProvider(sport=sport, metrics_client=metrics_client)

    response = await provider.get_teams()

    assert len(response.teams) == 48
    assert not any(team.eliminated for team in response.teams)
    metrics_client.increment.assert_called_once_with("wcs.cache_error", tags={"endpoint": "teams"})
