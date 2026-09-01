"""Integration tests for merino/curated_recommendations/corpus_backends/scheduled_surface_backend.py"""

import asyncio
import freezegun
import logging
import pytest

from circuitbreaker import STATE_HALF_OPEN, CircuitBreakerMonitor
from datetime import datetime, timedelta
from httpx import AsyncClient, HTTPStatusError, Response
from pydantic import HttpUrl
from tests.types import FilterCaplogFixture
from unittest.mock import AsyncMock

from merino.curated_recommendations.corpus_backends.circuitbreaker import (
    CuratedRecommendationsCircuitBreaker,
)
from merino.curated_recommendations.corpus_backends.protocol import (
    SurfaceId,
    CorpusItem,
    Topic,
)
from merino.curated_recommendations.corpus_backends.scheduled_surface_backend import (
    ScheduledSurfaceBackend,
)
from merino.curated_recommendations.corpus_backends.utils import (
    CorpusApiGraphConfig,
    CorpusGraphQLError,
)
from merino.exceptions import BackendError
from merino.utils.metrics import get_metrics_client


logger = logging.getLogger(__name__)


@pytest.fixture()
def make_scheduled_surface_backend(manifest_provider):
    """Return a factory for ScheduledSurfaceBackend instances with a given HTTP client.

    Each instance gets its own empty stale-while-revalidate cache, but they all
    share the class-level circuit breaker.
    """

    def _make(http_client: AsyncMock) -> ScheduledSurfaceBackend:
        return ScheduledSurfaceBackend(
            http_client=http_client,
            graph_config=CorpusApiGraphConfig(),
            metrics_client=get_metrics_client(),
            manifest_provider=manifest_provider,
        )

    return _make


@pytest.fixture()
def scheduled_surface_circuit_breaker():
    """Return the scheduled surface circuit breaker, closed before and after the test.

    The breaker decorates ScheduledSurfaceBackend.fetch at class-definition time, so a
    single instance is shared by every backend instance and every test.
    """
    breaker = CircuitBreakerMonitor.get(SCHEDULED_SURFACE_BREAKER_NAME)

    breaker.reset()

    yield breaker

    breaker.reset()


def make_http_client(
    response: Response | None = None, error: Exception | None = None
) -> AsyncMock:
    """Build a mock HTTP client that returns a fixed response or raises a fixed error."""
    http_client = AsyncMock(spec=AsyncClient)

    if error is not None:
        http_client.post.side_effect = error
    else:
        http_client.post.return_value = response

    return http_client


async def trip_breaker(make_scheduled_surface_backend, fixture_request_data) -> None:
    """Drive the shared breaker open through a real fetch against a failing API."""
    backend = make_scheduled_surface_backend(
        make_http_client(Response(status_code=503, request=fixture_request_data))
    )

    with pytest.raises(HTTPStatusError):
        await backend.fetch(SurfaceId.NEW_TAB_EN_US)


@pytest.mark.asyncio
async def test_fetch(scheduled_surface_backend: ScheduledSurfaceBackend):
    """Test if the fetch method returns data from cache if available."""
    surface_id = SurfaceId.NEW_TAB_EN_US

    # Populate the cache by calling the fetch method
    results = await scheduled_surface_backend.fetch(surface_id)

    assert len(results) == 160
    assert results[0] == CorpusItem(
        url=HttpUrl(
            "https://getpocket.com/explore/item/milk-powder-is-the-key-to-better-cookies-"
            "brownies-and-cakes?utm_source=firefox-newtab-en-us"
        ),
        title="Milk Powder Is the Key to Better Cookies, Brownies, and Cakes",
        excerpt="Consider this pantry staple your secret ingredient for making more flavorful "
        "desserts.",
        topic=Topic.FOOD,
        publisher="Epicurious",
        isTimeSensitive=False,
        imageUrl=HttpUrl(
            "https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/"
            "40e30ce2-a298-4b34-ab58-8f0f3910ee39.jpeg"
        ),
        scheduledCorpusItemId="de614b6b-6df6-470a-97f2-30344c56c1b3",
        corpusItemId="4095b364-02ff-402c-b58a-792a067fccf2",
        iconUrl=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_input,expected_title",
    [
        ({}, "Scheduled items from day 0"),  # Default value is 0
        ({"days_offset": 0}, "Scheduled items from day 0"),
        ({"days_offset": -1}, "Scheduled items from day -1"),
        ({"days_offset": -2}, "Scheduled items from day -2"),
        ({"days_offset": 1}, "Scheduled items from day 1"),
    ],
)
async def test_fetch_days_since_today(
    scheduled_surface_backend: ScheduledSurfaceBackend,
    fixture_request_data,
    scheduled_surface_http_client,
    test_input,
    expected_title,
):
    """Test fetch method with days_offset parameter."""
    surface_id = SurfaceId.NEW_TAB_EN_US

    def mock_post_by_date(*args, **kwargs):
        """Mock scheduledSurface response containing a single item with the schedule date."""
        variables = kwargs["json"]["variables"]
        surface_timezone = scheduled_surface_backend.get_surface_timezone(
            variables["scheduledSurfaceId"]
        )
        date_today = scheduled_surface_backend.get_scheduled_surface_date(surface_timezone).date()
        days_ago = (datetime.strptime(variables.get("date"), "%Y-%m-%d").date() - date_today).days
        return Response(
            status_code=200,
            json={
                "data": {
                    "scheduledSurface": {
                        "items": [
                            {
                                "id": "de614b6b-6df6-470a-97f2-30344c56c1b3",
                                "corpusItem": {
                                    "id": "f00ba411-6df6-470a-97f2-30344c56c1b3",
                                    "url": "https://example.com",
                                    "title": f"Scheduled items from day {days_ago}",
                                    "excerpt": "",
                                    "topic": "FOOD",
                                    "publisher": "Mozilla",
                                    "isTimeSensitive": True,
                                    "imageUrl": "https://example.com/image.jpg",
                                },
                            },
                        ]
                    }
                },
            },
            request=fixture_request_data,
        )

    scheduled_surface_http_client.post.side_effect = mock_post_by_date

    results = await scheduled_surface_backend.fetch(surface_id, **test_input)
    assert len(results) == 1
    assert results[0].title == expected_title


SCHEDULED_SURFACE_BREAKER_NAME = "curated_recommendations_scheduled_surface_circuit_breaker"
FAILURE_THRESHOLD = CuratedRecommendationsCircuitBreaker.FAILURE_THRESHOLD
RECOVERY_TIMEOUT = CuratedRecommendationsCircuitBreaker.RECOVERY_TIMEOUT


class TestScheduledSurfaceCircuitBreaker:
    """Tests covering the circuit breaker wrapped around SectionsBackend.fetch."""

    @pytest.mark.asyncio
    async def test_breaker_stays_closed_on_success(
        self, sections_backend: ScheduledSurfaceBackend, scheduled_surface_circuit_breaker
    ):
        """A successful fetch should leave the breaker closed with no failures recorded."""
        sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert sections
        assert scheduled_surface_circuit_breaker.closed
        assert scheduled_surface_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_breaker_opens_on_http_error(
        self,
        make_scheduled_surface_backend,
        fixture_request_data,
        scheduled_surface_circuit_breaker,
    ):
        """An HTTP error should exhaust the retries below the breaker, then open it."""
        http_client = make_http_client(Response(status_code=503, request=fixture_request_data))
        backend = make_scheduled_surface_backend(http_client)

        with pytest.raises(HTTPStatusError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        # @retry is applied below the breaker, so the breaker only sees one
        # failure once every attempt has been used up.
        assert http_client.post.call_count == ScheduledSurfaceBackend.retry_count
        assert scheduled_surface_circuit_breaker.failure_count == FAILURE_THRESHOLD
        assert scheduled_surface_circuit_breaker.opened

    @pytest.mark.asyncio
    async def test_breaker_opens_on_graphql_error(
        self,
        make_scheduled_surface_backend,
        fixture_graphql_200ok_with_error_response,
        fixture_request_data,
        scheduled_surface_circuit_breaker,
    ):
        """A 200 response carrying GraphQL errors should also open the breaker."""
        http_client = make_http_client(
            Response(
                status_code=200,
                json=fixture_graphql_200ok_with_error_response,
                request=fixture_request_data,
            )
        )
        backend = make_scheduled_surface_backend(http_client)

        with pytest.raises(CorpusGraphQLError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert http_client.post.call_count == ScheduledSurfaceBackend.retry_count
        assert scheduled_surface_circuit_breaker.opened

    @pytest.mark.asyncio
    async def test_breaker_ignores_unexpected_exceptions(
        self, make_scheduled_surface_backend, scheduled_surface_circuit_breaker
    ):
        """Errors outside EXPECTED_EXCEPTION should neither be retried nor open the breaker."""
        http_client = make_http_client(error=RuntimeError("not a corpus API error"))
        backend = make_scheduled_surface_backend(http_client)

        with pytest.raises(RuntimeError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert http_client.post.call_count == 1
        assert scheduled_surface_circuit_breaker.failure_count == 0
        assert scheduled_surface_circuit_breaker.closed

    @pytest.mark.asyncio
    async def test_breaker_short_circuits_while_open(
        self,
        make_scheduled_surface_backend,
        sections_http_client: AsyncMock,
        fixture_request_data,
        scheduled_surface_circuit_breaker,
    ):
        """While open, fetch should fail fast with BackendError and skip the API entirely."""
        await trip_breaker(make_scheduled_surface_backend, fixture_request_data)
        assert scheduled_surface_circuit_breaker.opened

        # A brand new backend with an empty cache and a healthy HTTP client is
        # still short-circuited: the breaker is shared across all instances.
        healthy_backend = make_scheduled_surface_backend(sections_http_client)

        with pytest.raises(BackendError, match="circuitbreaker"):
            await healthy_backend.fetch(SurfaceId.NEW_TAB_EN_US)

        sections_http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_breaker_serves_stale_cache(
        self,
        make_scheduled_surface_backend,
        scheduled_surface_http_client: AsyncMock,
        fixture_request_data,
        scheduled_surface_circuit_breaker,
        caplog,
        filter_caplog: FilterCaplogFixture,
    ):
        """The fallback must raise so @stale_while_revalidate can serve stale data."""
        caplog.set_level(logging.ERROR)

        backend = make_scheduled_surface_backend(scheduled_surface_http_client)

        # control time so we can expire the SWR cache
        with freezegun.freeze_time(tick=True) as time_gem:
            # populate the SWR cache
            cache_fresh = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert scheduled_surface_http_client.post.call_count == 1

            # Fast-forward past the max TTL with a margin: freezegun's tick() advances
            # from the freeze start, so real time spent since freezing is not counted.
            time_gem.tick(
                delta=ScheduledSurfaceBackend.cache_time_to_live_max + timedelta(minutes=1)
            )

            # open the circuit breaker
            await trip_breaker(make_scheduled_surface_backend, fixture_request_data)

            # with the circuit breaker open, we should get the expired cache
            cache_stale = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert cache_stale == cache_fresh

            # await the async call spawned by the cache so we can verify if an http
            # call was made
            await asyncio.gather(*list(backend._background_tasks))

            # with the breaker open, we should still only have 1 http call
            # (from the initial successful fetch)
            assert scheduled_surface_http_client.post.call_count == 1

            records = filter_caplog(
                caplog.records, "merino.curated_recommendations.corpus_backends.caching"
            )
            assert any("Returning stale data" in record.message for record in records)

    @pytest.mark.asyncio
    async def test_breaker_recovers_after_timeout(
        self,
        make_scheduled_surface_backend,
        scheduled_surface_http_client: AsyncMock,
        fixture_request_data,
        scheduled_surface_circuit_breaker,
    ):
        """After the recovery timeout the breaker half-opens, then closes on a good fetch."""
        with freezegun.freeze_time(tick=True) as time_gem:
            await trip_breaker(make_scheduled_surface_backend, fixture_request_data)

            assert scheduled_surface_circuit_breaker.opened

            # Advance past the recovery timeout with a margin: freezegun's tick() advances
            # from the freeze start, so the real time trip_breaker consumed is not counted.
            time_gem.tick(RECOVERY_TIMEOUT + 60)

            assert scheduled_surface_circuit_breaker.state == STATE_HALF_OPEN

            backend = make_scheduled_surface_backend(scheduled_surface_http_client)
            sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert sections

            scheduled_surface_http_client.post.assert_called_once()

            assert scheduled_surface_circuit_breaker.closed
            assert scheduled_surface_circuit_breaker.failure_count == 0
