"""Unit tests for the Elastic Backend."""

import datetime
import json
import logging
from typing import cast, Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import freezegun
import pytest

from elasticsearch import BadRequestError, ConflictError
from elastic_transport import ApiResponseMeta, HttpHeaders, NodeConfig
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Event

from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    get_index_settings,
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
        date=int(datetime.datetime.now().timestamp()),
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

    logger = logging.getLogger(
        "merino.providers.suggest.sports.backends.sportsdata.common.elastic"
    )
    with mock.patch.object(logger, "info") as mock_logger:
        await sport_data_store.store_events(sport=nfl, language_code="en")
        calls = [call.args[0] for call in mock_logger.call_args_list]
        assert len(list(filter(lambda x: "sports.time.load.events" in x, calls))) == 1
        assert len(list(filter(lambda x: "sports.time.load.refresh_indexes" in x, calls))) == 1


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


@pytest.mark.asyncio
async def test_get_index_settings():
    """Test that the settings are stripped if we're running local elastic search"""
    settings = get_index_settings(dsn="normal")
    assert "lowercase" in settings["analysis"]["filter"]
    assert "accentfolding" in settings["analysis"]["filter"]
    assert "accentfolding" in settings["analysis"]["analyzer"]["stop_analyzer_en"]["filter"]
    assert "accentfolding" in settings["analysis"]["analyzer"]["stop_analyzer_search_en"]["filter"]

    settings = get_index_settings(dsn="localhost")
    assert "lowercase" not in settings["analysis"]["filter"]
    assert "accentfolding" not in settings["analysis"]["filter"]
    assert "accentfolding" not in settings["analysis"]["analyzer"]["stop_analyzer_en"]["filter"]
    assert (
        "accentfolding"
        not in settings["analysis"]["analyzer"]["stop_analyzer_search_en"]["filter"]
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
    assert es_client.indices.create.call_count == 2
    assert any(
        [
            arg_list.kwargs.get("index") == META_INDEX
            for arg_list in es_client.indices.create.call_args_list
        ]
    )


@pytest.mark.asyncio
async def test_bad_creds():
    """Test failure if credentials are not present"""
    store = SportsDataStore(dsn="", api_key="", languages=["en"], platform="sports", index_map={})
    with pytest.raises(SportsDataError):
        await store.startup()
    store = SportsDataStore(
        dsn="bogus", api_key="", languages=["en"], platform="sports", index_map={}
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
    es_client.indices.create.side_effect = [br]
    await sport_data_store.build_indexes(clear=True)
    assert es_client.indices.delete.called
    assert es_client.indices.create.called
