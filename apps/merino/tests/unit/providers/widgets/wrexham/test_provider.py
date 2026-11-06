# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget provider."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham.protocol import MatchesResponse, MatchStatus
from merino.providers.widgets.wrexham.provider import (
    CURRENT_STATUSES,
    PREVIOUS_STATUSES,
    UPCOMING_STATUSES,
    WrexhamDataUnavailableError,
    WrexhamProvider,
)
from merino.providers.widgets.wrexham.store import WrexhamStore
from tests.types import FilterCaplogFixture
from tests.unit.providers.widgets.wrexham.conftest import MakeMatch, MakeStanding

CHAMPIONSHIP_ID = 34
FA_CUP_ID = 27
KICKOFF = datetime(2026, 11, 2, 15, tzinfo=UTC)


def _ids(matches: MatchesResponse) -> tuple[list[int], list[int], list[int]]:
    """Return the match IDs in each group."""
    return (
        [match.id for match in matches.previous],
        [match.id for match in matches.current],
        [match.id for match in matches.upcoming],
    )


@pytest.fixture(name="provider")
def fixture_provider(store: WrexhamStore, statsd_mock: Any) -> WrexhamProvider:
    """Return a provider that reads from the store."""
    return WrexhamProvider(store=store, metrics_client=statsd_mock, mock_data_enabled=False)


@pytest.fixture(name="mock_provider")
def fixture_mock_provider(store: WrexhamStore, statsd_mock: Any) -> WrexhamProvider:
    """Return a provider that serves mock data."""
    return WrexhamProvider(store=store, metrics_client=statsd_mock, mock_data_enabled=True)


@pytest.mark.asyncio
async def test_mock_matches_apply_limit_to_previous_and_upcoming(
    mock_provider: WrexhamProvider,
) -> None:
    """`limit` caps previous and upcoming mock matches but not current ones."""
    matches = await mock_provider.get_matches(limit=2)

    assert len(matches.previous) == 2
    assert len(matches.upcoming) == 2
    assert len(matches.current) == 1


@pytest.mark.asyncio
async def test_matches_are_grouped_and_ordered_by_status(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """Matches are grouped by status, with previous newest first and the rest earliest first."""
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [
            make_match(1, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=14)),
            make_match(2, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=7)),
            make_match(3, MatchStatus.Canceled, kickoff=KICKOFF - timedelta(days=3)),
            make_match(4, MatchStatus.InProgress, kickoff=KICKOFF),
            make_match(5, MatchStatus.Postponed, kickoff=KICKOFF + timedelta(days=7)),
            make_match(6, MatchStatus.Scheduled, kickoff=KICKOFF + timedelta(days=3)),
        ],
    )
    await store.write_fixtures(FA_CUP_ID, [])

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([3, 2, 1], [4], [6, 5])


@pytest.mark.asyncio
async def test_matches_combine_both_competitions(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """Championship and FA Cup matches are merged into one list."""
    await store.write_fixtures(
        CHAMPIONSHIP_ID, [make_match(1, MatchStatus.Scheduled, kickoff=KICKOFF)]
    )
    await store.write_fixtures(
        FA_CUP_ID,
        [
            make_match(
                2,
                MatchStatus.Scheduled,
                competition_id=FA_CUP_ID,
                kickoff=KICKOFF + timedelta(days=1),
            )
        ],
    )

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([], [], [1, 2])


@pytest.mark.asyncio
async def test_current_statuses_are_all_current(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """In progress, break, delayed and suspended matches are all current."""
    statuses = [
        MatchStatus.InProgress,
        MatchStatus.Break,
        MatchStatus.Delayed,
        MatchStatus.Suspended,
    ]
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [
            make_match(match_id, status, kickoff=KICKOFF + timedelta(hours=match_id))
            for match_id, status in enumerate(statuses, start=1)
        ],
    )

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([], [1, 2, 3, 4], [])


def test_every_status_is_in_exactly_one_group() -> None:
    """Each match status belongs to one group, so no match is ever left out."""
    groups = [PREVIOUS_STATUSES, CURRENT_STATUSES, UPCOMING_STATUSES]

    for status in MatchStatus:
        assert sum(status in group for group in groups) == 1, status


@pytest.mark.asyncio
async def test_limit_keeps_the_closest_previous_and_upcoming_matches(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """`limit` keeps the most recent results and the next fixtures, but not current matches."""
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [
            *[
                make_match(day, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=day))
                for day in range(1, 4)
            ],
            make_match(10, MatchStatus.InProgress, kickoff=KICKOFF),
            make_match(11, MatchStatus.Break, kickoff=KICKOFF),
            *[
                make_match(20 + day, MatchStatus.Scheduled, kickoff=KICKOFF + timedelta(days=day))
                for day in range(1, 4)
            ],
        ],
    )

    matches = await provider.get_matches(limit=1)

    assert _ids(matches) == ([1], [10, 11], [21])


@pytest.mark.asyncio
async def test_live_data_replaces_fixture_data(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """A live update moves a match between groups and replaces its fixture data."""
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [
            make_match(1, MatchStatus.Scheduled, kickoff=KICKOFF),
            make_match(2, MatchStatus.InProgress, kickoff=KICKOFF - timedelta(days=1)),
        ],
    )
    await store.write_live_matches(
        [
            make_match(1, MatchStatus.InProgress, kickoff=KICKOFF),
            make_match(2, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=1)),
        ]
    )

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([2], [1], [])
    assert matches.current[0].clock == "60"


@pytest.mark.asyncio
async def test_older_live_data_does_not_replace_newer_fixture_data(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """Fixture data is kept when it was updated after the live data, e.g. if live updates
    stopped.
    """
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [make_match(1, MatchStatus.Final, updated_at=KICKOFF + timedelta(hours=2))],
    )
    await store.write_live_matches(
        [make_match(1, MatchStatus.InProgress, updated_at=KICKOFF + timedelta(hours=1))]
    )

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([1], [], [])


@pytest.mark.asyncio
async def test_live_match_missing_from_fixtures_is_included(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """A live match that isn't in the fixtures yet is still returned."""
    await store.write_fixtures(CHAMPIONSHIP_ID, [])
    await store.write_live_matches([make_match(1, MatchStatus.InProgress)])

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([], [1], [])


@pytest.mark.asyncio
async def test_empty_fixtures_return_empty_groups(
    provider: WrexhamProvider, store: WrexhamStore
) -> None:
    """Stored but empty fixtures return empty groups rather than an error."""
    await store.write_fixtures(CHAMPIONSHIP_ID, [])
    await store.write_fixtures(FA_CUP_ID, [])

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([], [], [])


@pytest.mark.asyncio
async def test_one_missing_competition_still_returns_the_other(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """If only one competition's fixtures are stored, its matches are still returned."""
    await store.write_fixtures(CHAMPIONSHIP_ID, [make_match(1, MatchStatus.Scheduled)])

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([], [], [1])


@pytest.mark.asyncio
async def test_raises_when_no_fixtures_are_stored(
    provider: WrexhamProvider,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Raises WrexhamDataUnavailableError and logs when no fixtures are stored."""
    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_matches(limit=5)

    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.provider")
    assert [record.message for record in records] == ["No Wrexham fixtures are stored in Redis"]


@pytest.mark.asyncio
async def test_raises_logs_and_counts_redis_errors(
    store: WrexhamStore,
    statsd_mock: Any,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """A Redis read failure is logged, counted and raised as WrexhamDataUnavailableError."""
    mocker.patch.object(store, "read_fixtures", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store, metrics_client=statsd_mock, mock_data_enabled=False)

    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_matches(limit=5)

    statsd_mock.increment.assert_called_once_with(
        "widgets.wrexham.redis.error", tags={"data": "matches"}
    )
    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.provider")
    assert [record.message for record in records] == ["Could not read Wrexham matches from Redis"]


@pytest.mark.asyncio
async def test_get_standings_returns_the_mock_table(mock_provider: WrexhamProvider) -> None:
    """Returns the full mock Championship table when mock data is enabled."""
    standings = await mock_provider.get_standings()

    assert len(standings.standings) == 24


@pytest.mark.asyncio
async def test_get_standings_returns_the_stored_table_by_position(
    provider: WrexhamProvider, store: WrexhamStore, make_standing: MakeStanding
) -> None:
    """Returns the stored Championship table, ordered by league position."""
    await store.write_standings([make_standing(3), make_standing(1), make_standing(2)])

    standings = await provider.get_standings()

    assert standings.competition.name == "EFL Championship"
    assert [row.position for row in standings.standings] == [1, 2, 3]


@pytest.mark.asyncio
async def test_get_standings_returns_an_empty_stored_table(
    provider: WrexhamProvider, store: WrexhamStore
) -> None:
    """Returns an empty table when the stored table is empty, e.g. before the season starts."""
    await store.write_standings([])

    standings = await provider.get_standings()

    assert standings.standings == []


@pytest.mark.asyncio
async def test_get_standings_raises_when_no_standings_are_stored(
    provider: WrexhamProvider,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """Raises WrexhamDataUnavailableError and logs when no standings are stored."""
    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_standings()

    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.provider")
    assert [record.message for record in records] == ["No Wrexham standings are stored in Redis"]


@pytest.mark.asyncio
async def test_get_standings_raises_logs_and_counts_redis_errors(
    store: WrexhamStore,
    statsd_mock: Any,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """A Redis read failure is logged, counted and raised as WrexhamDataUnavailableError."""
    mocker.patch.object(store, "read_standings", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store, metrics_client=statsd_mock, mock_data_enabled=False)

    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_standings()

    statsd_mock.increment.assert_called_once_with(
        "widgets.wrexham.redis.error", tags={"data": "standings"}
    )
    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.provider")
    assert [record.message for record in records] == [
        "Could not read Wrexham standings from Redis"
    ]


@pytest.mark.asyncio
async def test_shutdown_closes_the_redis_connection(
    provider: WrexhamProvider, mocker: MockerFixture
) -> None:
    """Shutting down closes the store's cache connection."""
    close = mocker.patch.object(provider.store.cache, "close")

    await provider.shutdown()

    close.assert_awaited_once()
