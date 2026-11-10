# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget provider."""

from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

import pytest
from freezegun import freeze_time
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino import governance
from merino.configs import settings
from merino.exceptions import CacheAdapterError
from merino.providers.widgets.wrexham import metrics
from merino.providers.widgets.wrexham.protocol import MatchesResponse, MatchStatus
from merino.providers.widgets.wrexham.provider import (
    CURRENT_STATUSES,
    PREVIOUS_STATUSES,
    UPCOMING_STATUSES,
    WrexhamDataUnavailableError,
    WrexhamProvider,
    circuit_breaker,
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


@pytest.fixture(name="api_metrics")
def fixture_api_metrics(mocker: MockerFixture) -> Any:
    """Patch the API's OpenTelemetry instruments with mocks."""
    return mocker.Mock(
        redis_errors=mocker.patch.object(metrics, "api_redis_error_count"),
        data_age=mocker.patch.object(metrics, "api_data_age"),
    )


@pytest.fixture(name="provider")
def fixture_provider(store: WrexhamStore) -> WrexhamProvider:
    """Return a provider that reads from the store."""
    return WrexhamProvider(store=store)


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
    api_metrics: Any,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """A Redis read failure is logged, counted and raised as WrexhamDataUnavailableError."""
    mocker.patch.object(store, "read_fixtures", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store)

    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_matches(limit=5)

    api_metrics.redis_errors.add.assert_called_once_with(1, {"endpoint": "matches"})
    records = filter_caplog(caplog.records, "merino.providers.widgets.wrexham.provider")
    assert [record.message for record in records] == ["Could not read Wrexham matches from Redis"]


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
    api_metrics: Any,
    mocker: MockerFixture,
    caplog: LogCaptureFixture,
    filter_caplog: FilterCaplogFixture,
) -> None:
    """A Redis read failure is logged, counted and raised as WrexhamDataUnavailableError."""
    mocker.patch.object(store, "read_standings", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store)

    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_standings()

    api_metrics.redis_errors.add.assert_called_once_with(1, {"endpoint": "standings"})
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


FAILURE_THRESHOLD = settings.widgets.providers.wrexham.circuit_breaker_failure_threshold
RECOVERY_TIMEOUT = settings.widgets.providers.wrexham.circuit_breaker_recover_timeout_sec


@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_stays_open_after_redis_errors(
    store: WrexhamStore, api_metrics: Any, mocker: MockerFixture
) -> None:
    """After repeated Redis errors, matches return unavailable without calling Redis. Each
    Redis error is counted, and the breaker gauge reports it as open.
    """
    read_fixtures = mocker.patch.object(
        store, "read_fixtures", side_effect=CacheAdapterError("Redis is down")
    )
    provider = WrexhamProvider(store=store)

    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)

    assert circuit_breaker.opened
    assert read_fixtures.await_count == FAILURE_THRESHOLD

    for _ in range(3):
        with pytest.raises(WrexhamDataUnavailableError, match="circuit breaker is open"):
            await provider.get_matches(limit=5)

    assert read_fixtures.await_count == FAILURE_THRESHOLD
    assert api_metrics.redis_errors.add.call_count == FAILURE_THRESHOLD
    assert metrics.circuit_breaker_open_value(circuit_breaker) == 1


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_once_redis_works_again(
    store: WrexhamStore, mocker: MockerFixture, make_match: MakeMatch
) -> None:
    """After the recovery timeout, a successful Redis read closes the breaker."""
    read_fixtures = mocker.patch.object(
        store, "read_fixtures", side_effect=CacheAdapterError("Redis is down")
    )
    provider = WrexhamProvider(store=store)
    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)
    assert circuit_breaker.opened

    read_fixtures.side_effect = None
    read_fixtures.return_value = ([make_match(1)], KICKOFF)
    mocker.patch("circuitbreaker.monotonic", return_value=monotonic() + RECOVERY_TIMEOUT + 1)

    matches = await provider.get_matches(limit=5)

    assert _ids(matches) == ([1], [], [])
    assert circuit_breaker.closed


@pytest.mark.asyncio
async def test_circuit_breaker_gauge_follows_the_breaker_state(
    store: WrexhamStore, mocker: MockerFixture
) -> None:
    """The gauge is 0 while closed, 1 while open, 0 again while half-open, and 1 once a
    failed read reopens the breaker.
    """
    mocker.patch.object(store, "read_fixtures", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store)
    assert metrics.circuit_breaker_open_value(circuit_breaker) == 0

    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)
    assert metrics.circuit_breaker_open_value(circuit_breaker) == 1

    mocker.patch("circuitbreaker.monotonic", return_value=monotonic() + RECOVERY_TIMEOUT + 1)
    assert metrics.circuit_breaker_open_value(circuit_breaker) == 0  # Half-open.

    with pytest.raises(WrexhamDataUnavailableError):
        await provider.get_matches(limit=5)
    assert metrics.circuit_breaker_open_value(circuit_breaker) == 1


def test_observe_circuit_breaker_reports_the_breaker_state(mocker: MockerFixture) -> None:
    """The observable gauge's callback reports whether the breaker is open."""
    create_gauge = mocker.patch.object(metrics._meter, "create_observable_gauge")
    breaker = mocker.Mock(opened=True)

    metrics.observe_circuit_breaker(breaker)

    create_gauge.assert_called_once()
    assert create_gauge.call_args.kwargs["name"] == "merino.wrexham.api.circuit_breaker.open"
    [callback] = create_gauge.call_args.kwargs["callbacks"]
    assert [observation.value for observation in callback(mocker.Mock())] == [1]
    breaker.opened = False
    assert [observation.value for observation in callback(mocker.Mock())] == [0]


@pytest.mark.asyncio
@freeze_time(KICKOFF)
async def test_matches_record_the_age_of_each_stored_data_type(
    provider: WrexhamProvider,
    store: WrexhamStore,
    api_metrics: Any,
    mocker: MockerFixture,
    make_match: MakeMatch,
) -> None:
    """The age of the fixtures for each competition, and of the live data, is recorded."""
    fetched_at = {
        CHAMPIONSHIP_ID: KICKOFF - timedelta(minutes=30),
        FA_CUP_ID: KICKOFF - timedelta(hours=1),
    }
    mocker.patch.object(
        store,
        "read_fixtures",
        side_effect=lambda competition_id: ([make_match(1)], fetched_at[competition_id]),
    )
    mocker.patch.object(
        store, "read_live_matches", return_value=([], KICKOFF - timedelta(seconds=45))
    )

    await provider.get_matches(limit=5)

    assert api_metrics.data_age.record.call_args_list == [
        mocker.call(
            1800.0,
            {"endpoint": "matches", "data_type": "fixtures", "competition": "EFL Championship"},
        ),
        mocker.call(
            3600.0, {"endpoint": "matches", "data_type": "fixtures", "competition": "FA Cup"}
        ),
        mocker.call(45.0, {"endpoint": "matches", "data_type": "live_matches"}),
    ]


@pytest.mark.asyncio
@freeze_time(KICKOFF)
async def test_standings_record_the_age_of_the_stored_table(
    provider: WrexhamProvider, store: WrexhamStore, api_metrics: Any, mocker: MockerFixture
) -> None:
    """The age of the stored standings is recorded."""
    mocker.patch.object(store, "read_standings", return_value=([], KICKOFF - timedelta(hours=2)))

    await provider.get_standings()

    api_metrics.data_age.record.assert_called_once_with(
        7200.0, {"endpoint": "standings", "data_type": "standings"}
    )


@pytest.mark.asyncio
async def test_missing_data_does_not_trip_the_circuit_breaker(
    provider: WrexhamProvider,
) -> None:
    """Having no fixtures stored isn't a Redis failure, so the breaker stays closed."""
    for _ in range(FAILURE_THRESHOLD + 1):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)

    assert circuit_breaker.closed


@pytest.mark.asyncio
async def test_standings_redis_errors_open_the_circuit_breaker(
    store: WrexhamStore, api_metrics: Any, mocker: MockerFixture
) -> None:
    """Repeated Redis errors reading standings open the breaker too."""
    read_standings = mocker.patch.object(
        store, "read_standings", side_effect=CacheAdapterError("Redis is down")
    )
    provider = WrexhamProvider(store=store)

    for _ in range(FAILURE_THRESHOLD + 3):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_standings()

    assert circuit_breaker.opened
    assert read_standings.await_count == FAILURE_THRESHOLD
    assert api_metrics.redis_errors.add.call_count == FAILURE_THRESHOLD


@pytest.mark.asyncio
async def test_open_circuit_breaker_blocks_both_endpoints(
    store: WrexhamStore,
    mocker: MockerFixture,
    make_standing: MakeStanding,
) -> None:
    """Both endpoints share the breaker, so once it opens, standings aren't read either."""
    mocker.patch.object(store, "read_fixtures", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store)
    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)
    await store.write_standings([make_standing(1)])
    read_standings = mocker.spy(store, "read_standings")

    with pytest.raises(WrexhamDataUnavailableError, match="circuit breaker is open"):
        await provider.get_standings()

    read_standings.assert_not_called()


@pytest.mark.asyncio
async def test_open_circuit_breaker_is_reported_by_governance(
    store: WrexhamStore, mocker: MockerFixture
) -> None:
    """An open breaker shows up in the governance circuit breaker metrics."""
    mocker.patch.object(store, "read_fixtures", side_effect=CacheAdapterError("Redis is down"))
    provider = WrexhamProvider(store=store)
    for _ in range(FAILURE_THRESHOLD):
        with pytest.raises(WrexhamDataUnavailableError):
            await provider.get_matches(limit=5)
    metrics_client = mocker.patch.object(governance.governing, "metrics_client")

    await governance.governing.cron()

    metrics_client.gauge.assert_any_call("governance.circuits.wrexham", value=FAILURE_THRESHOLD)


# Two hours after kickoff: a normal match has just finished.
FULL_TIME_CHECK = KICKOFF + timedelta(hours=2)


@pytest.mark.parametrize(
    ("kickoff", "updated_at", "group"),
    [
        (KICKOFF, FULL_TIME_CHECK - timedelta(minutes=2), "current"),
        (KICKOFF, FULL_TIME_CHECK - timedelta(minutes=5), "current"),
        (KICKOFF, FULL_TIME_CHECK - timedelta(minutes=6), "previous"),
        (KICKOFF - timedelta(hours=4), FULL_TIME_CHECK - timedelta(minutes=1), "previous"),
        (KICKOFF - timedelta(days=1), FULL_TIME_CHECK - timedelta(minutes=1), "previous"),
        (FULL_TIME_CHECK + timedelta(days=7), FULL_TIME_CHECK, "previous"),
    ],
    ids=[
        "just-finished",
        "end-of-grace-period",
        "after-grace-period",
        "updated-hours-after-kickoff",
        "updated-the-next-day",
        "future-awarded-match",
    ],
)
@pytest.mark.asyncio
@freeze_time(FULL_TIME_CHECK)
async def test_finished_matches_stay_current_during_the_grace_period(
    provider: WrexhamProvider,
    store: WrexhamStore,
    make_match: MakeMatch,
    kickoff: datetime,
    updated_at: datetime,
    group: str,
) -> None:
    """A match that just finished stays in current for 5 minutes. Later updates to a match
    that finished long ago, or a final result for a future match, don't move it back.
    """
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [make_match(1, MatchStatus.Final, kickoff=kickoff, updated_at=updated_at)],
    )

    matches = await provider.get_matches(limit=5)

    expected: tuple[list[int], list[int], list[int]] = (
        ([], [1], []) if group == "current" else ([1], [], [])
    )
    assert _ids(matches) == expected


@pytest.mark.asyncio
@freeze_time(FULL_TIME_CHECK)
async def test_just_finished_matches_dont_count_towards_the_previous_limit(
    provider: WrexhamProvider, store: WrexhamStore, make_match: MakeMatch
) -> None:
    """The limit applies to the older finished matches, not the one still in current."""
    await store.write_fixtures(
        CHAMPIONSHIP_ID,
        [
            make_match(1, MatchStatus.Final, kickoff=KICKOFF, updated_at=FULL_TIME_CHECK),
            make_match(2, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=7)),
            make_match(3, MatchStatus.Final, kickoff=KICKOFF - timedelta(days=14)),
        ],
    )

    matches = await provider.get_matches(limit=1)

    assert _ids(matches) == ([2], [1], [])
