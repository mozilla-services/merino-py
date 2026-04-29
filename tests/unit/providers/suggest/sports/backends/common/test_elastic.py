"""Unit tests for the Elastic Backend."""

import datetime
import json
import logging
from typing import Any, cast
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import freezegun
import pytest

from dynaconf import LazySettings
from elasticsearch import ApiError, BadRequestError, ConflictError
from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event

from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    ElasticCredentials,
    META_INDEX,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import NFL


@pytest.fixture(name="es_client")
def fixture_es_client(mocker: MockerFixture) -> MagicMock:
    """Test ElasticSearch client instance."""
    client = mocker.MagicMock()
    client.options = MagicMock(name="options", return_value=client)
    client.close = mocker.AsyncMock()

    indices = mocker.MagicMock()
    indices.create = mocker.AsyncMock()
    indices.delete = mocker.AsyncMock()
    indices.refresh = mocker.AsyncMock()
    client.indices = indices

    client.delete_by_query = mocker.AsyncMock()
    client.delete = mocker.AsyncMock()
    client.search = mocker.AsyncMock()
    return cast(MagicMock, client)


@pytest.fixture(name="sport_data_store")
def fixture_sport_data_store(es_client: MagicMock, statsd_mock: Any) -> SportsDataStore:
    """Test Sport Data Store instance."""
    creds = ElasticCredentials(dsn="http://es.test:9200", api_key="test-key")
    s = SportsDataStore(
        credentials=creds,
        languages=["en"],
        platform="test",
        index_map={"event": "sports-en-events"},
        metrics_client=statsd_mock,
    )
    s.client = es_client
    return s


@pytest.mark.asyncio
async def test_credentials():
    """Try all paths for known settings"""
    test_settings = LazySettings()
    test = ElasticCredentials(settings=test_settings)
    assert not test.validate()
    test_settings.jobs = LazySettings()
    test_settings.jobs.wikipedia_indexer = LazySettings()
    test_settings.jobs.wikipedia_indexer.es_url = "http://localhost:9200"
    test = ElasticCredentials(settings=test_settings)
    assert not test.validate()
    test_settings.jobs.wikipedia_indexer.es_api_key = "test_key"
    test = ElasticCredentials(settings=test_settings)
    assert test.validate()
    test_settings = LazySettings()
    test = ElasticCredentials(settings=test_settings)
    assert not test.validate()
    test_settings.providers = LazySettings()
    test_settings.providers.wikipedia = LazySettings()
    test_settings.providers.wikipedia.es_url = "http://127.0.0.1:9200"
    test_settings.providers.wikipedia.es_api_key = "test_key"
    test = ElasticCredentials(settings=test_settings)
    assert test.validate()
    test_settings = LazySettings()
    test_settings.providers = LazySettings()
    test_settings.providers.sports = LazySettings()
    test_settings.providers.sports.es = LazySettings()
    test_settings.providers.sports.es.dsn = "http://localhost:9200"
    test_settings.providers.sports.es.api_key = "test-key"
    test = ElasticCredentials(settings=test_settings)
    assert test.validate()


@pytest.mark.asyncio
async def test_create_raise_exception(
    sport_data_store: SportsDataStore, es_client: AsyncMock
) -> None:
    """Test Sport Data Store create raises exception."""
    es_client.indices.create.side_effect = BadRequestError("oops", cast(Any, object()), {})

    with pytest.raises(SportsDataError):
        await sport_data_store.build_indexes()


@pytest.mark.asyncio
async def test_prune_fail_and_logging_captured(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    mocker: MockerFixture,
) -> None:
    """Test Sport Data Store fail prune and metrics captured."""
    es_client.delete_by_query.side_effect = ConflictError("oops", cast(Any, object()), {})
    logger = logging.getLogger(
        "merino.providers.suggest.sports.backends.sportsdata.common.elastic"
    )
    with mock.patch.object(logger, "warning") as mock_logger:
        result = await sport_data_store.prune()
        assert result is False
        assert mock_logger.called


@pytest.mark.asyncio
async def test_store_event_fail_and_metrics_captured(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    mocker: MockerFixture,
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
        expiry=datetime.datetime.now(),
        updated=datetime.datetime.now(),
    )
    nfl = NFL(settings=settings.providers.sports)
    nfl.events = {0: event}

    logger = logging.getLogger(
        "merino.providers.suggest.sports.backends.sportsdata.common.elastic"
    )
    with mock.patch.object(logger, "info") as mock_logger:
        await sport_data_store.store_events(sport=nfl, language_code="en")
        calls = [call.args[0] for call in mock_logger.call_args_list]
        assert len(list(filter(lambda x: "sports.time.load.events" in x, calls))) == 1
        assert len(list(filter(lambda x: "sports.time.load.refresh_indexes" in x, calls))) == 1


@pytest.mark.asyncio
async def test_store_events_bulk_called_once_for_multiple_events(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    mocker: MockerFixture,
) -> None:
    """Test that store_events calls async_bulk once with all events, not once per event.

    Regression test for a bug where async_bulk was called inside the action collection
    loop, resulting in n*(n+1)/2 writes per job rather than n.
    """
    action_count = 3
    mock_async_bulk = mocker.patch(
        f"{SportsDataStore.__module__}.helpers.async_bulk",
        new_callable=AsyncMock,
        return_value=(action_count, []),
    )
    nfl = NFL(settings=settings.providers.sports)
    nfl.events = {
        i: Event(
            sport="football",
            id=i,
            terms="test",
            date=datetime.datetime.now(),
            original_date="2025-09-22",
            home_team={"key": f"home{i}"},
            home_score=0,
            away_team={"key": f"away{i}"},
            away_score=0,
            status=GameStatus.Scheduled,
            expiry=datetime.datetime.now(),
            updated=datetime.datetime.now(),
        )
        for i in range(action_count)
    }

    await sport_data_store.store_events(sport=nfl, language_code="en")

    assert mock_async_bulk.call_count == 1
    actions = mock_async_bulk.call_args.kwargs["actions"]
    assert len(actions) == action_count


@freezegun.freeze_time("2025-09-22T12:00:00Z")
@pytest.mark.asyncio
async def test_sports_search_event_hits(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
):
    """Test Sport Data Store search event with a hit."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    hits = [
        {
            "_score": 0.1,
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Final",
                        "label": "alpha",
                        "date": (now - datetime.timedelta(seconds=3700)).isoformat(),
                        "updated": (now - datetime.timedelta(seconds=3700)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 0.2,  # Most recently updated game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Final",
                        "label": "beta",
                        "date": (now - datetime.timedelta(seconds=3700)).isoformat(),
                        "updated": (now - datetime.timedelta(seconds=3600)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 1.0,  # Current game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "InProgress",
                        "label": "epsilon",
                        "date": (now - datetime.timedelta(seconds=100)).isoformat(),
                        "updated": (now - datetime.timedelta(seconds=1)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 1.0,  # Current game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "InProgress",
                        "label": "gamma",
                        "date": (now - datetime.timedelta(seconds=100)).isoformat(),
                        "updated": now.isoformat(),
                    }
                )
            },
        },
        {
            "_score": 2.0,  # Next scheduled game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Scheduled",
                        "label": "delta",
                        "date": (now + datetime.timedelta(seconds=3 * 86400)).isoformat(),
                        "updated": now.isoformat(),
                    }
                )
            },
        },
        {
            "_score": 2.1,  # Future scheduled game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Scheduled",
                        "label": "epsilon",
                        "date": (now + datetime.timedelta(seconds=2 * 86400)).isoformat(),
                        "updated": now.isoformat(),
                    }
                )
            },
        },
    ]
    es_client.search.return_value = {"hits": {"total": {"value": 1}, "hits": hits}}

    result = await sport_data_store.search_events(q="game", language_code="en", mix_sports=False)
    expected_result = {
        "NFL": {
            "current": {
                "date": "2025-09-22T11:58:20+00:00",
                "es_score": 1.0,
                "event_status": GameStatus.InProgress,
                "label": "gamma",
                "sport": "NFL",
                "status": "InProgress",
                "touched": "None",
                "updated": "2025-09-22T12:00:00+00:00",
            },
            "next": {
                "date": "2025-09-25T12:00:00+00:00",
                "es_score": 2.0,
                "event_status": GameStatus.Scheduled,
                "label": "delta",
                "sport": "NFL",
                "status": "Scheduled",
                "touched": "None",
                "updated": "2025-09-22T12:00:00+00:00",
            },
        }
    }

    assert result == expected_result


@freezegun.freeze_time("2025-09-22T12:00:00Z")
@pytest.mark.asyncio
async def test_sports_search_event_hits_no_current(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
):
    """Test Sport Data Store search event with a hit."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    hits = [
        {
            "_score": 0.1,  # A prior game.
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Final",
                        "label": "alpha",
                        "date": (now - datetime.timedelta(seconds=3800)).isoformat(),
                        "updated": (now - datetime.timedelta(seconds=3809)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 0.2,  # Most recently played & updated game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Final",
                        "label": "beta",
                        "date": (now - datetime.timedelta(seconds=3700)).isoformat(),
                        "updated": (now - datetime.timedelta(seconds=3600)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 2.0,  # Next scheduled game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Scheduled",
                        "label": "delta",
                        "date": (now + datetime.timedelta(seconds=3 * 86400)).isoformat(),
                    }
                )
            },
        },
        {
            "_score": 2.1,  # Future scheduled game
            "_source": {
                "event": json.dumps(
                    {
                        "sport": "NFL",
                        "status": "Scheduled",
                        "epsilondate": (now + datetime.timedelta(seconds=2 * 86400)).isoformat(),
                    }
                )
            },
        },
    ]
    es_client.search.return_value = {"hits": {"total": {"value": 1}, "hits": hits}}

    result = await sport_data_store.search_events(q="game", language_code="en", mix_sports=False)
    expected_result = {
        "NFL": {
            "previous": {
                "date": "2025-09-22T10:58:20+00:00",
                "es_score": 0.2,
                "event_status": GameStatus.Final,
                "label": "beta",
                "sport": "NFL",
                "status": "Final",
                "touched": "None",
                "updated": "2025-09-22T11:00:00+00:00",
            },
            "next": {
                "date": "2025-09-25T12:00:00+00:00",
                "es_score": 2.0,
                "event_status": GameStatus.Scheduled,
                "label": "delta",
                "sport": "NFL",
                "status": "Scheduled",
                "touched": "None",
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


@freezegun.freeze_time("2025-09-22T12:00:00Z")
@pytest.mark.asyncio
async def test_search_events_count_metric_on_success(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that a successful search increments the count metric."""
    es_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

    await sport_data_store.search_events(q="game", language_code="en")

    statsd_mock.increment.assert_called_once_with(
        "es.search.count", tags={"index": "sports-en-events"}
    )


@pytest.mark.asyncio
async def test_search_events_error_metric_on_api_error(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that an ApiError increments both the count and error metrics."""
    api_error = ApiError(
        message="service unavailable",
        meta=ApiResponseMeta(
            status=503,
            http_version="",
            headers=HttpHeaders(),
            duration=0.0,
            node=NodeConfig(scheme="", host="", port=0),
        ),
        body={},
    )
    es_client.search.side_effect = api_error

    with pytest.raises(BackendError):
        await sport_data_store.search_events(q="game", language_code="en")

    statsd_mock.increment.assert_any_call("es.search.count", tags={"index": "sports-en-events"})
    statsd_mock.increment.assert_any_call(
        "es.search.error", tags={"index": "sports-en-events", "status": 503}
    )


@pytest.mark.asyncio
async def test_search_events_error_metric_on_exception(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that a generic exception increments both the count and error metrics."""
    es_client.search.side_effect = Exception("connection reset")

    with pytest.raises(BackendError):
        await sport_data_store.search_events(q="game", language_code="en")

    statsd_mock.increment.assert_any_call("es.search.count", tags={"index": "sports-en-events"})
    statsd_mock.increment.assert_any_call(
        "es.search.error", tags={"index": "sports-en-events", "status": "unknown"}
    )


@pytest.mark.asyncio
async def test_query_meta_count_metric_on_success(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that a successful query_meta increments the count metric."""
    es_client.search.return_value = {"hits": {"hits": []}}

    await sport_data_store.query_meta("last_update")

    statsd_mock.increment.assert_any_call("es.search.count", tags={"index": META_INDEX})


@pytest.mark.asyncio
async def test_query_meta_error_metric_on_api_error(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that an ApiError in query_meta increments both count and error metrics."""
    api_error = ApiError(
        message="service unavailable",
        meta=ApiResponseMeta(
            status=503,
            http_version="",
            headers=HttpHeaders(),
            duration=0.0,
            node=NodeConfig(scheme="", host="", port=0),
        ),
        body={},
    )
    es_client.search.side_effect = api_error

    result = await sport_data_store.query_meta("last_update")

    assert result is None
    statsd_mock.increment.assert_any_call("es.search.count", tags={"index": META_INDEX})
    statsd_mock.increment.assert_any_call(
        "es.search.error", tags={"index": META_INDEX, "status": 503}
    )


@pytest.mark.asyncio
async def test_query_meta_error_metric_on_exception(
    sport_data_store: SportsDataStore,
    es_client: AsyncMock,
    statsd_mock: Any,
):
    """Test that a generic exception in query_meta increments both count and error metrics."""
    es_client.search.side_effect = Exception("connection reset")

    result = await sport_data_store.query_meta("last_update")

    assert result is None
    statsd_mock.increment.assert_any_call("es.search.count", tags={"index": META_INDEX})
    statsd_mock.increment.assert_any_call(
        "es.search.error", tags={"index": META_INDEX, "status": "unknown"}
    )


@pytest.mark.asyncio
async def test_meta_store(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test storing data to meta"""
    es_client.create.side_effect = ConflictError("oops", cast(Any, object()), {})
    await sport_data_store.store_meta("foo", "bar")
    assert es_client.create.called
    assert es_client.update.called


@pytest.mark.asyncio
async def test_meta_query(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test query data to meta"""
    es_client.search.return_value = {"hits": {}}
    res = await sport_data_store.query_meta("foo")
    assert res is None
    es_client.search.return_value = {"hits": {"hits": [{"_source": {"meta_value": "bar"}}]}}
    res = await sport_data_store.query_meta("foo")
    assert res == "bar"


@pytest.mark.asyncio
async def test_meta_del(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test deleting data to meta"""
    await sport_data_store.del_meta("foo")
    assert es_client.delete.called
    assert es_client.indices.refresh.called


@pytest.mark.asyncio
async def test_meta_build(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test building indexes for meta"""
    await sport_data_store.build_meta()

    assert es_client.indices.create.called
    assert es_client.indices.refresh.called


@pytest.mark.asyncio
async def test_build_indexes(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test the index builder"""
    await sport_data_store.build_indexes(clear=True)
    assert es_client.indices.delete.called
    assert es_client.indices.create.called


@pytest.mark.asyncio
async def test_build_meta(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test the index builder"""
    await sport_data_store.build_meta()
    assert es_client.indices.create.called


@pytest.mark.asyncio
async def test_startup(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test startup initializer"""
    # Check for initial case.
    es_client.search.return_value = {"hits": {"hits": []}}
    await sport_data_store.startup()
    assert es_client.indices.create.call_count == 0
    await sport_data_store.build_indexes()
    assert es_client.indices.create.call_count == 2
    assert any(
        [
            arg_list.kwargs.get("index") == META_INDEX
            for arg_list in es_client.indices.create.call_args_list
        ]
    )


@pytest.mark.asyncio
async def test_bad_creds(statsd_mock: Any):
    """Test failure if credentials are not present"""
    creds = ElasticCredentials(dsn="", api_key="")
    store = SportsDataStore(
        credentials=creds,
        languages=["en"],
        platform="sports",
        index_map={},
        metrics_client=statsd_mock,
    )
    with pytest.raises(SportsDataError):
        await store.startup()
    creds = ElasticCredentials(dsn="bogus", api_key="")
    store = SportsDataStore(
        credentials=creds,
        languages=["en"],
        platform="sports",
        index_map={},
        metrics_client=statsd_mock,
    )
    with pytest.raises(SportsDataError):
        await store.startup()


@pytest.mark.asyncio
async def test_build_index_exception(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test failed create"""
    br = BadRequestError(
        message="resource_already_exists_exception",
        meta=ApiResponseMeta(
            status=400,
            http_version="",
            headers=HttpHeaders(),
            duration=0.0,
            node=NodeConfig(scheme="", host="", port=0),
        ),
        body="oops",
        errors=(),
    )
    es_client.indices.create.side_effect = [br, br]
    await sport_data_store.build_indexes(clear=True)
    assert es_client.indices.delete.called
    assert es_client.indices.create.called


@pytest.mark.asyncio
async def test_shutdown(sport_data_store: SportsDataStore, es_client: AsyncMock):
    """Test shutdown"""
    # note: test cov does not believe that sport_data_store.client is set.
    await sport_data_store.shutdown()
    assert es_client.close.called
