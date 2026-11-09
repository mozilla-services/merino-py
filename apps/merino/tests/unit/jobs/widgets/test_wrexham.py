# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget ingestion job."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import HttpUrl
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.jobs.widgets.wrexham import TEAM_SHORT_NAMES, WrexhamIngester, use_short_names
from merino.providers.widgets.wrexham.protocol import (
    CHAMPIONSHIP,
    FA_CUP,
    Competition,
    Match,
    MatchStatus,
    Standing,
    Team,
)
from merino.providers.widgets.wrexham.sportsdata import SportsDataBackend, SportsDataBackendError
from merino.providers.widgets.wrexham.store import WrexhamStore
from tests.types import FilterCaplogFixture

SEASON = 2027
INTERVAL = timedelta(minutes=10)
LOGO = HttpUrl("https://test-cdn.mozilla.net/logo.png")


def match(match_id: int, competition: Competition, hour: int) -> Match:
    """Return a scheduled match kicking off at `hour` today."""
    team = Team(id=1, name="Team", logo_url=LOGO)
    return Match(
        id=match_id,
        competition=competition,
        kickoff=datetime(2026, 11, 4, hour, tzinfo=UTC),
        home_team=team,
        away_team=team,
        period=None,
        status=MatchStatus.Scheduled,
        clock=None,
        home_score=None,
        away_score=None,
        home_penalty_score=None,
        away_penalty_score=None,
        updated_at=datetime(2026, 11, 4, tzinfo=UTC),
    )


@pytest.fixture(name="backend")
def fixture_backend(mocker: MockerFixture) -> Any:
    """Return a backend mock returning one match per competition."""
    backend = mocker.AsyncMock(spec=SportsDataBackend)
    backend.fetch_schedule.side_effect = lambda competition, season: [match(1, competition, 12)]
    backend.fetch_live_matches.side_effect = lambda competition: [
        match(2, CHAMPIONSHIP, 20) if competition == CHAMPIONSHIP else match(3, FA_CUP, 15)
    ]
    backend.fetch_standings.return_value = []
    return backend


@pytest.fixture(name="store")
def fixture_store(mocker: MockerFixture) -> Any:
    """Return a store mock."""
    return mocker.AsyncMock(spec=WrexhamStore)


@pytest.fixture(name="ingester")
def fixture_ingester(backend: Any, store: Any) -> WrexhamIngester:
    """Return an ingester with mock backend and store."""
    return WrexhamIngester(
        backend=backend,
        store=store,
        season=SEASON,
        fixtures_interval=INTERVAL,
        standings_interval=INTERVAL,
    )


@pytest.mark.asyncio
async def test_first_run_refreshes_everything(
    ingester: WrexhamIngester,
    backend: Any,
    store: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Write fixtures per competition, live matches once and by kickoff, and standings, and log
    each refresh.
    """
    caplog.set_level(logging.INFO)

    await ingester.run_once()

    assert [call.args[0] for call in store.write_fixtures.call_args_list] == [
        CHAMPIONSHIP.id,
        FA_CUP.id,
    ]
    [live] = store.write_live_matches.call_args.args
    assert [m.id for m in live] == [3, 2]
    backend.fetch_standings.assert_awaited_once_with(CHAMPIONSHIP, SEASON)
    store.write_standings.assert_awaited_once_with([])
    records = filter_caplog(caplog.records, "merino.jobs.widgets.wrexham")
    assert [(r.__dict__["refresh"], r.levelno) for r in records] == [
        ("live_matches", logging.INFO),
        ("fixtures", logging.INFO),
        ("fixtures", logging.INFO),
        ("standings", logging.INFO),
    ]
    assert records[0].__dict__["match_count"] == 2


@pytest.mark.asyncio
async def test_fixtures_and_standings_wait_for_their_interval(
    ingester: WrexhamIngester, backend: Any, mocker: MockerFixture
) -> None:
    """Refresh live matches every run, fixtures and standings only once their interval passes."""
    clock = mocker.patch("merino.jobs.widgets.wrexham.monotonic", return_value=1000.0)
    await ingester.run_once()

    clock.return_value = 1000.0 + INTERVAL.total_seconds() - 1
    await ingester.run_once()
    assert backend.fetch_live_matches.await_count == 4  # Two runs, two competitions.
    assert backend.fetch_standings.await_count == 1
    assert backend.fetch_schedule.await_count == 2  # One run, two competitions.

    clock.return_value = 1000.0 + INTERVAL.total_seconds()
    await ingester.run_once()
    assert backend.fetch_standings.await_count == 2
    assert backend.fetch_schedule.await_count == 4


@pytest.mark.asyncio
async def test_failures_are_isolated(
    ingester: WrexhamIngester,
    backend: Any,
    store: Any,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """A failed refresh, or competition, is logged and doesn't stop the others. A live failure
    in any competition writes no live matches.
    """
    caplog.set_level(logging.ERROR)
    error = SportsDataBackendError("boom")
    backend.fetch_standings.side_effect = error
    backend.fetch_live_matches.side_effect = [[match(2, CHAMPIONSHIP, 20)], error]
    backend.fetch_schedule.side_effect = [error, [match(1, FA_CUP, 12)]]

    await ingester.run_once()

    store.write_live_matches.assert_not_awaited()
    store.write_standings.assert_not_awaited()
    store.write_fixtures.assert_awaited_once_with(FA_CUP.id, [match(1, FA_CUP, 12)])
    records = filter_caplog(caplog.records, "merino.jobs.widgets.wrexham")
    assert sorted(r.__dict__["refresh"] for r in records) == [
        "fixtures",
        "live_matches",
        "standings",
    ]


@pytest.mark.asyncio
async def test_run_loop_runs_until_stop_event(ingester: WrexhamIngester, store: Any) -> None:
    """Run every interval, and exit as soon as the stop event is set."""
    stop_event = asyncio.Event()
    runs = 0

    def count_run(matches: list[Match]) -> None:
        nonlocal runs
        runs += 1
        if runs == 2:
            stop_event.set()

    store.write_live_matches.side_effect = count_run

    await asyncio.wait_for(ingester.run_loop(0.01, stop_event), timeout=1)

    assert runs == 2


@pytest.mark.asyncio
async def test_shutdown_closes_connections(
    ingester: WrexhamIngester, backend: Any, store: Any, mocker: MockerFixture
) -> None:
    """Close the SportsDataIO client and the Redis connection."""
    store.cache = mocker.AsyncMock()

    await ingester.shutdown()

    backend.shutdown.assert_awaited_once()
    store.cache.close.assert_awaited_once()


WREXHAM_ID = 90002327
CARDIFF_ID = 90001461
NEW_TEAM_ID = 1  # A team in neither the fallback table nor the standings.


def match_between(home_id: int, away_id: int) -> Match:
    """Return a match between two teams whose names are the full names."""
    return match(1, CHAMPIONSHIP, 12).model_copy(
        update={
            "home_team": Team(id=home_id, name=f"Full name {home_id}", logo_url=LOGO),
            "away_team": Team(id=away_id, name=f"Full name {away_id}", logo_url=LOGO),
        }
    )


def standing(team_id: int, short_name: str) -> Standing:
    """Return a table row for a team, named with its short name as SportsDataIO gives it."""
    team = Team(id=team_id, name=short_name, logo_url=LOGO)
    return Standing(position=1, team=team, played=12, goal_difference=0, points=20)


def test_use_short_names_replaces_known_teams_only() -> None:
    """Teams with a short name get it; other teams keep their full name."""
    [result] = use_short_names([match_between(WREXHAM_ID, NEW_TEAM_ID)], {WREXHAM_ID: "Wrexham"})

    assert (result.home_team.name, result.away_team.name) == ("Wrexham", "Full name 1")


@pytest.mark.asyncio
async def test_first_run_uses_the_fallback_short_names(
    ingester: WrexhamIngester, backend: Any, store: Any
) -> None:
    """Before any standings are fetched, fixtures and live matches use the fallback table."""
    backend.fetch_schedule.side_effect = lambda competition, season: [
        match_between(WREXHAM_ID, CARDIFF_ID)
    ]
    backend.fetch_live_matches.side_effect = lambda competition: [
        match_between(CARDIFF_ID, NEW_TEAM_ID)
    ]

    await ingester.run_once()

    _, fixtures = store.write_fixtures.call_args_list[0].args
    assert (fixtures[0].home_team.name, fixtures[0].away_team.name) == (
        TEAM_SHORT_NAMES[WREXHAM_ID],
        TEAM_SHORT_NAMES[CARDIFF_ID],
    )
    [live] = store.write_live_matches.call_args.args
    assert (live[0].home_team.name, live[0].away_team.name) == (
        TEAM_SHORT_NAMES[CARDIFF_ID],
        "Full name 1",
    )


@pytest.mark.asyncio
async def test_later_runs_use_short_names_from_the_standings(
    ingester: WrexhamIngester, backend: Any, store: Any
) -> None:
    """After a standings refresh, its short names are used, and fallback teams that aren't
    in the table keep theirs.
    """
    backend.fetch_standings.return_value = [
        standing(WREXHAM_ID, "Wrexham AFC (table)"),
        standing(NEW_TEAM_ID, "New Team"),
    ]
    backend.fetch_live_matches.side_effect = lambda competition: [
        match_between(WREXHAM_ID, NEW_TEAM_ID)
        if competition == CHAMPIONSHIP
        else match_between(CARDIFF_ID, NEW_TEAM_ID)
    ]
    await ingester.run_once()  # Live matches, fixtures, then standings.

    await ingester.run_once()  # Live matches only, now with the table's names.

    [live] = store.write_live_matches.call_args.args
    names = {(m.home_team.name, m.away_team.name) for m in live}
    assert names == {
        ("Wrexham AFC (table)", "New Team"),
        (TEAM_SHORT_NAMES[CARDIFF_ID], "New Team"),
    }


@pytest.mark.asyncio
async def test_failed_standings_refresh_keeps_the_short_names(
    ingester: WrexhamIngester, backend: Any, store: Any
) -> None:
    """If a standings refresh fails, the short names already in use are kept."""
    backend.fetch_standings.side_effect = SportsDataBackendError("boom")
    backend.fetch_live_matches.side_effect = lambda competition: [
        match_between(WREXHAM_ID, NEW_TEAM_ID)
    ]

    await ingester.run_once()
    await ingester.run_once()

    [live] = store.write_live_matches.call_args.args
    assert live[0].home_team.name == TEAM_SHORT_NAMES[WREXHAM_ID]
