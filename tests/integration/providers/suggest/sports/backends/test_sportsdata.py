"""Integration Tests for Sports."""

import logging

from datetime import datetime, timezone
from typing import Any

import freezegun
import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch
from testcontainers.elasticsearch import ElasticSearchContainer

from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.data import Team, Event
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    ElasticDataStore,
    ElasticCredentials,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import NFL
from merino.providers.suggest.sports.backends.sportsdata.protocol import (
    SportSummary,
    SportEventDetail,
    SportTeamDetail,
)

logger = logging.getLogger(__name__)
FROZEN_TIME = datetime(2025, 10, 27, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def es_url():
    """ElasticSearch URL fixture."""
    with ElasticSearchContainer("docker.elastic.co/elasticsearch/elasticsearch:8.13.4") as es:
        url = es.get_url()
        yield url


@pytest_asyncio.fixture
async def es_client(es_url):
    """Elasticsearch client fixture."""
    client = AsyncElasticsearch(es_url, verify_certs=False, ssl_show_warn=False)
    try:
        await client.cluster.health(wait_for_status="yellow", timeout="10s")
        yield client
    finally:
        await client.close()


@pytest.fixture(name="sportsdata_parameters")
def fixture_sportsdata_parameters(
    statsd_mock: Any, es_client: AsyncElasticsearch
) -> dict[str, Any]:
    """Create constructor parameters for sportsdata provider."""
    return {
        "metrics_client": statsd_mock,
        "trigger_words": ["game", "game today"],
        "settings": {},
    }


@pytest.fixture(name="sport_data_store_parameters")
def fixture_sport_data_store_parameters(es_client) -> dict[str, Any]:
    """SportsDataStore constructor parameters."""
    return {
        "credentials": ElasticCredentials(dsn="", api_key=""),
        "languages": ["en"],
        "platform": "en_sports",
        "index_map": {
            "event": "{lang}_sports_event",
        },
    }


@pytest.fixture(name="sportsdata")
def fixture_sportsdata(
    sportsdata_parameters: dict[str, Any],
    sport_data_store_parameters: dict[str, Any],
    es_client: AsyncElasticsearch,
    monkeypatch,
) -> SportsDataBackend:
    """Create a SportsDataBackend instance."""

    def fake_init(self, *, credentials: ElasticCredentials, **kwargs):
        self.client = es_client

    monkeypatch.setattr(ElasticDataStore, "__init__", fake_init)

    return SportsDataBackend(
        **sportsdata_parameters,
        store=SportsDataStore(**sport_data_store_parameters, client=es_client),
    )


@pytest.fixture(name="sports_league")
def fixture_nfl() -> NFL:
    """Create a NFL instance for Testing."""
    frozen_time_int = int(FROZEN_TIME.timestamp())

    nfl = NFL(settings=settings.providers.sports)
    home = Team(
        terms="fake home",
        fullname="Fake Home",
        name="Home",
        key="HOM",
        locale="Home City",
        aliases=["Fake Home"],
        colors=["000000", "FFFFFF"],
        updated=FROZEN_TIME,
        expiry=frozen_time_int + 3600,
    ).minimal()
    away = Team(
        terms="fake away",
        fullname="Fake Away",
        name="Away",
        key="AWA",
        locale="Away City",
        aliases=["Fake Away"],
        colors=["000000", "FFFFFF"],
        updated=FROZEN_TIME,
        expiry=frozen_time_int + 3600,
    ).minimal()

    ev = Event(
        sport="football",
        id=1,
        terms="fakehome fakeaway",
        date=frozen_time_int + 600,
        original_date="2025-10-27",
        home_team=home,
        away_team=away,
        home_score=None,
        away_score=None,
        status=GameStatus.parse("Scheduled"),
        expiry=frozen_time_int + 3600,
    )

    nfl.events = {ev.id: ev}
    return nfl


@pytest.mark.asyncio
async def test_sportsdata_query_empty_store(sportsdata: SportsDataBackend):
    """Test query of empty store."""
    await sportsdata.data_store.build_indexes(clear=True)
    response = await sportsdata.query("fakehome")
    assert len(response) == 0


@freezegun.freeze_time("2025-10-26")
@pytest.mark.asyncio
async def test_sportsdata_na_query(sportsdata: SportsDataBackend, sports_league: NFL):
    """Test query of sportsdata."""
    # build indexes
    await sportsdata.data_store.build_indexes(clear=True)

    await sportsdata.data_store.store_events(sport=sports_league, language_code="en")
    result = await sportsdata.query("fakehome")

    expected_result = SportSummary(
        sport="all",
        values=[
            SportEventDetail(
                sport="football",
                query="football Fake Away at Fake Home 27 Oct 2025",
                date="2025-10-27T00:10:00+00:00",
                home_team=SportTeamDetail(
                    key="HOM", name="Fake Home", colors=["000000", "FFFFFF"], score=None
                ),
                away_team=SportTeamDetail(
                    key="AWA", name="Fake Away", colors=["000000", "FFFFFF"], score=None
                ),
                status_type="scheduled",
                status="Scheduled",
            )
        ],
    )

    assert len(result) == 1
    assert result[0] == expected_result


@freezegun.freeze_time("2025-10-26")
@pytest.mark.asyncio
async def test_sportsdata_query_with_no_result(sportsdata: SportsDataBackend, sports_league: NFL):
    """Test query of sportsdata."""
    # build indexes
    await sportsdata.data_store.build_indexes(clear=True)

    await sportsdata.data_store.store_events(sport=sports_league, language_code="en")
    response = await sportsdata.query("something else")
    assert len(response) == 0


@freezegun.freeze_time("2025-10-26")
@pytest.mark.asyncio
async def test_sportsdata_query_post_prune(sportsdata, sports_league: NFL):
    """Test query of sportsdata after pruning."""
    await sportsdata.data_store.build_indexes(clear=True)

    await sportsdata.data_store.store_events(sport=sports_league, language_code="en")
    results = await sportsdata.data_store.search_events("fakehome", "en")
    assert len(results) == 1

    now = int(datetime.now(tz=timezone.utc).timestamp())
    for ev in sports_league.events.values():
        ev.expiry = now - 5

    await sportsdata.data_store.store_events(sport=sports_league, language_code="en")

    pruned = await sportsdata.data_store.prune(language_code="en")
    assert pruned is True

    post_result = await sportsdata.data_store.search_events("fakehome", "en")
    assert post_result == {}
