"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import asyncio
import copy
import freezegun
import logging
import pytest

from httpx import AsyncClient, HTTPStatusError, Response
from tests.types import FilterCaplogFixture
from unittest.mock import AsyncMock

from circuitbreaker import STATE_HALF_OPEN, CircuitBreakerMonitor

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.circuitbreaker import (
    CuratedRecommendationsCircuitBreaker,
)
from merino.curated_recommendations.corpus_backends.protocol import CreateSource, SurfaceId
from merino.curated_recommendations.corpus_backends.utils import (
    CorpusApiGraphConfig,
    CorpusGraphQLError,
)
from merino.curated_recommendations.ml_backends.protocol import SpindleBackendProtocol
from merino.exceptions import BackendError
from merino.utils.metrics import get_metrics_client


@pytest.fixture()
def make_sections_backend(manifest_provider):
    """Return a factory for SectionsBackend instances with a given HTTP client.

    Each instance gets its own empty stale-while-revalidate cache, but they all
    share the class-level circuit breaker.
    """

    def _make(http_client: AsyncMock) -> SectionsBackend:
        return SectionsBackend(
            http_client=http_client,
            graph_config=CorpusApiGraphConfig(),
            metrics_client=get_metrics_client(),
            manifest_provider=manifest_provider,
        )

    return _make


@pytest.fixture()
def sections_circuit_breaker():
    """Return the sections circuit breaker, closed before and after the test.

    The breaker decorates SectionsBackend.fetch at class-definition time, so a
    single instance is shared by every backend instance and every test.
    """
    breaker = CircuitBreakerMonitor.get(SECTIONS_BREAKER_NAME)

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


async def trip_breaker(make_sections_backend, fixture_request_data) -> None:
    """Drive the shared breaker open through a real fetch against a failing API."""
    backend = make_sections_backend(
        make_http_client(Response(status_code=503, request=fixture_request_data))
    )

    with pytest.raises(HTTPStatusError):
        await backend.fetch(SurfaceId.NEW_TAB_EN_US)


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)
    # We no longer expect crawl sections from fixtures.
    assert all(not section.externalId.endswith("_crawl") for section in sections), (
        "Fixture should not contain crawl sections"
    )
    assert len(sections) >= 20, f"Expected at least 20 sections in fixture, got {len(sections)}"

    # Check that we have exactly 1 section with createSource == "MANUAL"
    manual_sections = [s for s in sections if s.createSource == CreateSource.MANUAL]
    assert len(manual_sections) == 1, f"Expected 1 MANUAL section, got {len(manual_sections)}"
    assert manual_sections[0].title == "Tech stuff"
    assert manual_sections[0].variantId is None

    # Lookup the NFL section by its externalId.
    nfl = next(s for s in sections if s.externalId == "nfl")
    assert nfl.title == "NFL"
    assert nfl.iab.taxonomy == "IAB-3.0"  # IAB v3.0 is used
    assert nfl.iab.categories[0] == "484"  # IAB v3.0 code for American Football
    # The number of items may vary based on test data
    assert len(nfl.sectionItems) >= 15

    # Lookup the Music section by its externalId.
    music = next(s for s in sections if s.externalId == "music")
    assert music is not None
    assert music.title == "Music"
    assert music.iab.taxonomy == "IAB-3.0"  # IAB v3.0 is used
    assert music.iab.categories[0] == "338"  # IAB v3.0 code for Music
    # The number of items may vary based on test data
    assert len(music.sectionItems) >= 15

    # Lookup Headlines section
    headlines = next(s for s in sections if s.externalId == "headlines")
    assert headlines is not None
    assert headlines.title == "Headlines"
    assert headlines.description == "Top Headlines today"


@pytest.mark.asyncio
async def test_fetch_ca_strips_locale_suffix(sections_ca_backend: SectionsBackend):
    """Test that CA sections have '__lEN_CA' suffix stripped from externalId."""
    sections = await sections_ca_backend.fetch(SurfaceId.NEW_TAB_EN_CA)
    assert len(sections) > 0, "Expected CA sections from fixture"

    # Verify no externalId retains the '__lEN_CA' suffix
    for section in sections:
        assert "__" not in section.externalId, (
            f"externalId '{section.externalId}' still contains locale suffix"
        )


@pytest.mark.asyncio
async def test_fetch_ie_strips_locale_suffix(sections_ie_backend: SectionsBackend):
    """Test that IE sections have '__lEN_IE' suffix stripped from externalId."""
    sections = await sections_ie_backend.fetch(SurfaceId.NEW_TAB_EN_IE)
    assert len(sections) > 0, "Expected IE sections from fixture"

    # Verify no externalId retains the '__lEN_IE' suffix
    for section in sections:
        assert "__" not in section.externalId, (
            f"externalId '{section.externalId}' still contains locale suffix"
        )


@pytest.mark.asyncio
async def test_fetch_preserves_experiment_suffix(
    sections_response_data, fixture_request_data, make_sections_backend
):
    """Experiment suffixes should be parsed into a canonical section with an alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050"

    http_client = make_http_client(
        Response(
            status_code=200,
            json=response_data,
            request=fixture_request_data,
        )
    )

    backend = make_sections_backend(http_client)

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government = next(section for section in sections if section.externalId == "government-test")
    assert government.variantId == 0
    assert government.alternateSection is not None
    assert government.alternateSection.variantId == 5050


@pytest.mark.asyncio
async def test_fetch_strips_locale_suffix_after_experiment_suffix(
    sections_response_data, fixture_request_data, make_sections_backend
):
    """Locale stripping should preserve experiment metadata when linking the alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050__lDE_DE"

    http_client = make_http_client(
        Response(
            status_code=200,
            json=response_data,
            request=fixture_request_data,
        )
    )

    backend = make_sections_backend(http_client)

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government = next(section for section in sections if section.externalId == "government-test")
    assert government.variantId == 0
    assert government.alternateSection is not None
    assert government.alternateSection.variantId == 5050


@pytest.mark.asyncio
async def test_fetch_links_experiment_variant_to_base_section(
    sections_response_data, fixture_request_data, make_sections_backend
):
    """A base/variant pair should be returned as one canonical section with an alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050"

    http_client = make_http_client(
        Response(
            status_code=200,
            json=response_data,
            request=fixture_request_data,
        )
    )

    backend = make_sections_backend(http_client)

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government_sections = [
        section for section in sections if section.externalId == "government-test"
    ]
    assert len(government_sections) == 1
    assert government_sections[0].variantId == 0
    assert government_sections[0].alternateSection is not None
    assert government_sections[0].alternateSection.variantId == 5050


class _StubSpindle(SpindleBackendProtocol):
    """Records refresh calls; getters return None."""

    def __init__(self):
        """Initialize with empty call log."""
        self.calls: list[tuple[int, SurfaceId]] = []

    async def refresh_duplicate_item_info(self, items, surface, threshold=0.85):
        """Record the call."""
        self.calls.append((len(items), surface))

    def get_similar_stories_text(self, surface):
        """No cache; tests only need refresh-call records."""
        return None

    def get_similar_stories_image(self, surface):
        """No cache."""
        return None


@pytest.mark.asyncio
async def test_fetch_schedules_spindle_refresh(
    sections_response_data, fixture_request_data, manifest_provider
):
    """Sections fetch should fire a background spindle refresh containing all items."""
    http_client = make_http_client(
        Response(
            status_code=200,
            json=sections_response_data,
            request=fixture_request_data,
        )
    )
    spindle = _StubSpindle()
    backend = SectionsBackend(
        http_client=http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
        spindle_backend=spindle,
    )

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)
    # Let the background task run.
    await asyncio.sleep(0)

    expected_count = sum(len(s.sectionItems) for s in sections)
    assert spindle.calls == [(expected_count, SurfaceId.NEW_TAB_EN_US)]


SECTIONS_BREAKER_NAME = "curated_recommendations_sections_circuit_breaker"
FAILURE_THRESHOLD = CuratedRecommendationsCircuitBreaker.FAILURE_THRESHOLD
RECOVERY_TIMEOUT = CuratedRecommendationsCircuitBreaker.RECOVERY_TIMEOUT


class TestSectionsCircuitBreaker:
    """Tests covering the circuit breaker wrapped around SectionsBackend.fetch."""

    @pytest.mark.asyncio
    async def test_breaker_stays_closed_on_success(
        self, sections_backend: SectionsBackend, sections_circuit_breaker
    ):
        """A successful fetch should leave the breaker closed with no failures recorded."""
        sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert sections
        assert sections_circuit_breaker.closed
        assert sections_circuit_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_breaker_opens_on_http_error(
        self, make_sections_backend, fixture_request_data, sections_circuit_breaker
    ):
        """An HTTP error should exhaust the retries below the breaker, then open it."""
        http_client = make_http_client(Response(status_code=503, request=fixture_request_data))
        backend = make_sections_backend(http_client)

        with pytest.raises(HTTPStatusError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        # @retry is applied below the breaker, so the breaker only sees one
        # failure once every attempt has been used up.
        assert http_client.post.call_count == SectionsBackend.retry_count
        assert sections_circuit_breaker.failure_count == FAILURE_THRESHOLD
        assert sections_circuit_breaker.opened

    @pytest.mark.asyncio
    async def test_breaker_opens_on_graphql_error(
        self,
        make_sections_backend,
        fixture_graphql_200ok_with_error_response,
        fixture_request_data,
        sections_circuit_breaker,
    ):
        """A 200 response carrying GraphQL errors should also open the breaker."""
        http_client = make_http_client(
            Response(
                status_code=200,
                json=fixture_graphql_200ok_with_error_response,
                request=fixture_request_data,
            )
        )
        backend = make_sections_backend(http_client)

        with pytest.raises(CorpusGraphQLError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert http_client.post.call_count == SectionsBackend.retry_count
        assert sections_circuit_breaker.opened

    @pytest.mark.asyncio
    async def test_breaker_ignores_unexpected_exceptions(
        self, make_sections_backend, sections_circuit_breaker
    ):
        """Errors outside EXPECTED_EXCEPTION should neither be retried nor open the breaker."""
        http_client = make_http_client(error=RuntimeError("not a corpus API error"))
        backend = make_sections_backend(http_client)

        with pytest.raises(RuntimeError):
            await backend.fetch(SurfaceId.NEW_TAB_EN_US)

        assert http_client.post.call_count == 1
        assert sections_circuit_breaker.failure_count == 0
        assert sections_circuit_breaker.closed

    @pytest.mark.asyncio
    async def test_breaker_short_circuits_while_open(
        self,
        make_sections_backend,
        sections_http_client: AsyncMock,
        fixture_request_data,
        sections_circuit_breaker,
    ):
        """While open, fetch should fail fast with BackendError and skip the API entirely."""
        await trip_breaker(make_sections_backend, fixture_request_data)
        assert sections_circuit_breaker.opened

        # A brand new backend with an empty cache and a healthy HTTP client is
        # still short-circuited: the breaker is shared across all instances.
        healthy_backend = make_sections_backend(sections_http_client)

        with pytest.raises(BackendError, match="circuitbreaker"):
            await healthy_backend.fetch(SurfaceId.NEW_TAB_EN_US)

        sections_http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_breaker_serves_stale_cache(
        self,
        make_sections_backend,
        sections_http_client: AsyncMock,
        fixture_request_data,
        caplog,
        filter_caplog: FilterCaplogFixture,
    ):
        """The fallback must raise so @stale_while_revalidate can serve stale data."""
        caplog.set_level(logging.ERROR)

        backend = make_sections_backend(sections_http_client)

        # control time so we can expire the SWR cache
        with freezegun.freeze_time(tick=True) as time_gem:
            # populate the SWR cache
            cache_fresh = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert sections_http_client.post.call_count == 1

            # fast-forward time so the cache expires
            time_gem.tick(delta=SectionsBackend.cache_time_to_live_max)

            # open the circuit breaker
            await trip_breaker(make_sections_backend, fixture_request_data)

            # with the circuit breaker open, we should get the expired cache
            cache_stale = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert cache_stale == cache_fresh

            # await the async call spawned by the cache so we can verify if an http
            # call was made
            await asyncio.gather(*list(backend._background_tasks))

            # with the breaker open, we should still only have 1 http call
            # (from the initial successful fetch)
            assert sections_http_client.post.call_count == 1

            records = filter_caplog(
                caplog.records, "merino.curated_recommendations.corpus_backends.caching"
            )
            assert any("Returning stale data" in record.message for record in records)

    @pytest.mark.asyncio
    async def test_breaker_recovers_after_timeout(
        self,
        make_sections_backend,
        sections_http_client: AsyncMock,
        fixture_request_data,
        sections_circuit_breaker,
    ):
        """After the recovery timeout the breaker half-opens, then closes on a good fetch."""
        with freezegun.freeze_time(tick=True) as time_gem:
            await trip_breaker(make_sections_backend, fixture_request_data)

            assert sections_circuit_breaker.opened

            # advance time so the circuit breaker recovers
            time_gem.tick(RECOVERY_TIMEOUT + 5)

            assert sections_circuit_breaker.state == STATE_HALF_OPEN

            backend = make_sections_backend(sections_http_client)
            sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

            assert sections

            sections_http_client.post.assert_called_once()

            assert sections_circuit_breaker.closed
            assert sections_circuit_breaker.failure_count == 0
