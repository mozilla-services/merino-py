# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for fetch_schedules.py module."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.jobs.sportsdata_jobs import SportDataUpdater

from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    ElasticCredentials,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    Sport,
    Event,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import SportsDataError


@pytest.fixture(name="httpx_client")
def fixture_httpx_client(mocker: MockerFixture) -> AsyncClient:
    """Define a mock httpx client"""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


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
def fixture_sport_data_store(es_client: MagicMock, statsd_mock: Any) -> SportsDataStore:
    """Test Sport Data Store instance"""
    creds = ElasticCredentials(dsn="http://es.test:9200", api_key="test-key")
    s = SportsDataStore(
        credentials=creds,
        languages=["en"],
        platform="test",
        index_map={"event": "sports-en-events-test"},
        metrics_client=statsd_mock,
    )
    s.client = es_client
    return s


@pytest.mark.asyncio
async def test_updater(
    sport_data_store: SportsDataStore,
    httpx_client: AsyncClient,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test provider functions:"""

    def new_sport() -> MagicMock:
        mock_sport = MagicMock(spec=Sport)
        mock_sport.name = "mock"
        mock_sport.events = {
            0: Event(
                sport=mock_sport.name,
                id=0,
                terms="",
                date=now,
                original_date="",
                home_team=dict(key="HOM", id=123),
                away_team=dict(key="AWY", id=456),
                home_score=0,
                away_score=0,
                status=GameStatus.Unknown,
                expiry=now + timedelta(seconds=300),
                updated=now,
            )
        }
        return mock_sport

    monkeypatch.setattr(settings.providers.sports, "sports", ["nfl", "NbA", "NHL", "NoneSuch"])
    updater = SportDataUpdater(settings=settings.providers.sports, store=sport_data_store)
    assert list(updater.sports.keys()) == ["NFL", "NBA", "NHL"]
    assert updater.store == sport_data_store

    now = datetime.now(tz=timezone.utc)
    mock_sport = new_sport()
    updater.sports = {"mock": mock_sport}
    updater.store.store_events = mocker.AsyncMock()  # type: ignore

    await updater.update_data(include_teams=True, client=httpx_client)
    assert mock_sport.update_teams.called
    assert updater.store.store_events.called  # type: ignore
    # prune() is not called.
    assert not sport_data_store.client.delete_by_query.called  # type: ignore

    sport_data_store.client.reset()  # type: ignore
    updater.store.store_events.reset()  # type: ignore
    mock_sport = new_sport()
    updater.sports = {"mock": mock_sport}
    await updater.nightly()
    assert mock_sport.update_teams.called
    assert sport_data_store.client.delete_by_query.called  # type: ignore
    assert not sport_data_store.client.store_events.called  # type: ignore

    sport_data_store.client.reset()  # type: ignore
    updater.store.store_events.reset()  # type: ignore
    mock_sport = new_sport()
    updater.sports = {"mock": mock_sport}
    await updater.quick_update()
    assert not mock_sport.update_teams.called
    assert mock_sport.update_events.called


@pytest.mark.asyncio
async def test_update_and_cache_wcs_closes_store_on_error(
    sport_data_store: SportsDataStore,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WCS cache updates should close the datastore when refresh work fails."""
    monkeypatch.setattr(settings.providers.sports, "sports", ["WCS"])
    updater = SportDataUpdater(settings=settings.providers.sports, store=sport_data_store)
    shutdown = mocker.AsyncMock()
    cast(Any, updater.store).startup = mocker.AsyncMock()
    cast(Any, updater.store).shutdown = shutdown
    cast(Any, updater).update_widget = mocker.AsyncMock()
    cast(Any, updater).update_data = mocker.AsyncMock(side_effect=SportsDataError("provider down"))
    mocker.patch("merino.jobs.sportsdata_jobs.monitor", return_value=nullcontext())

    with pytest.raises(SportsDataError):
        await updater.update_and_cache_wcs()

    shutdown.assert_awaited_once()
