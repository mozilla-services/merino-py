"""Unit tests for the Elastic Backend."""

import datetime
import json
from typing import cast, Any
from unittest.mock import AsyncMock, MagicMock

import freezegun
import pytest

from elasticsearch import BadRequestError, ConflictError
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event

from merino.providers.suggest.sports.backends.sportsdata.common.elastic import SportsDataStore
from merino.providers.suggest.sports.backends.sportsdata.common.error import SportsDataError
from merino.providers.suggest.sports.backends.sportsdata.common.sports import NFL


@pytest.fixture(name="es_client")
def fixture_es_client(mocker: MockerFixture) -> MagicMock:
    """Test ElasticSearch client instance."""
    client = mocker.MagicMock()
    client.close = mocker.AsyncMock()

    indices = mocker.MagicMock()
    indices.create = mocker.AsyncMock()
    indices.delete = mocker.AsyncMock()
    indices.refresh = mocker.AsyncMock()
    client.indices = indices

    client.delete_by_query = mocker.AsyncMock()
    client.search = mocker.AsyncMock()
    return cast(MagicMock, client)


@pytest.fixture(name="sport_data_store")
def fixture_sport_data_store(es_client: MagicMock) -> SportsDataStore:
    """Test Sport Data Store instance."""
    s = SportsDataStore(
        dsn="http://es.test:9200",
        api_key="test-key",
        languages=["en"],
        platform="test",
        index_map={"event": "sports-en-events"},
    )
    s.client = es_client
    return s


@pytest.mark.asyncio
async def test_create_raise_exception(
    sport_data_store: SportsDataStore, es_client: AsyncMock
) -> None:
    """Test Sport Data Store create raises exception."""
    es_client.indices.create.side_effect = BadRequestError("oops", cast(Any, object()), {})

    with pytest.raises(SportsDataError):
        await sport_data_store.build_indexes(settings=settings)


@pytest.mark.asyncio
async def test_prune_fail_and_metrics_captured(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
) -> None:
    """Test Sport Data Store fail prune and metrics captured."""
    es_client.delete_by_query.side_effect = ConflictError("oops", cast(Any, object()), {})

    result = await sport_data_store.prune(metrics_client=statsd_mock)
    assert result is False
    metrics_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_called == ["sports.time.prune"]


@pytest.mark.asyncio
async def test_store_event_fail_and_metrics_captured(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    mocker: MockerFixture,
    statsd_mock: Any,
) -> None:
    """Test Sport Data Store store_event fail and metrics captured."""
    mocker.patch(
        f"{SportsDataStore.__module__}.helpers.async_bulk",
        new_callable=AsyncMock,
        return_value=([], []),
    )
    event = Event(
        sport="football",
        id=0,
        terms="test",
        date=datetime.datetime.now(),
        original_date="2025-09-22",
        home_team={"key": "home"},
        home_score=0,
        away_team={"key": "away"},
        away_score=0,
        status=GameStatus.Scheduled,
        expiry=0,
    )
    nfl = NFL(settings=settings.providers.sports)
    nfl.events = {0: event}

    await sport_data_store.store_events(sport=nfl, language_code="en", metrics_client=statsd_mock)
    metrics_called = [call_arg[0][0] for call_arg in statsd_mock.timeit.call_args_list]
    assert metrics_called == ["sports.time.load.events", "sports.time.load.refresh_indexes"]


@freezegun.freeze_time("2025-09-22T12:00:00Z")
@pytest.mark.asyncio
async def test_search_event_hits(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
):
    """Test Sport Data Store search event with a hit."""
    now = int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
    hits = [
        {
            "_score": 1.0,
            "_source": {
                "event": json.dumps({"sport": "NFL", "status": "Final", "date": now - 3600})
            },
        },
        {
            "_score": 0.9,
            "_source": {
                "event": json.dumps({"sport": "NFL", "status": "InProgress", "date": now - 100})
            },
        },
        {
            "_score": 0.8,
            "_source": {
                "event": json.dumps(
                    {"sport": "NFL", "status": "Scheduled", "date": now + 3 * 86400}
                )
            },
        },
        {
            "_score": 0.7,
            "_source": {
                "event": json.dumps(
                    {"sport": "NFL", "status": "Scheduled", "date": now + 2 * 86400}
                )
            },
        },
    ]
    es_client.search.return_value = {"hits": {"total": {"value": 1}, "hits": hits}}

    result = await sport_data_store.search_events(q="game", language_code="en", mix_sports=False)
    expected_result = {
        "NFL": {
            "current": {
                "date": 1758542300,
                "es_score": 0.9,
                "event_status": GameStatus.InProgress,
                "sport": "NFL",
                "status": "InProgress",
            },
            "next": {
                "date": 1758801600,
                "es_score": 0.8,
                "event_status": GameStatus.Scheduled,
                "sport": "NFL",
                "status": "Scheduled",
            },
        }
    }

    assert result == expected_result


@pytest.mark.asyncio
async def test_search_event_bad_hit_data(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
):
    """Test Sport Data Store search event with a bad hit."""
    es_client.search.return_value = {"hits": {}}
    result = await sport_data_store.search_events(q="game", language_code="en", mix_sports=False)
    assert result == {}


@pytest.mark.asyncio
async def test_search_event_raise_exception(
    sport_data_store: SportsDataStore, es_client: AsyncMock
):
    """Test Sport Data Store search event raises exception."""
    es_client.search.side_effect = Exception("oops")
    with pytest.raises(BackendError):
        await sport_data_store.search_events(q="oops", language_code="en", mix_sports=False)
