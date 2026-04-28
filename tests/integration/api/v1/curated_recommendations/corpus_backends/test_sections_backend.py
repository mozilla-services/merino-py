"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import copy
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Response

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.protocol import CreateSource, SurfaceId
from merino.curated_recommendations.corpus_backends.utils import CorpusApiGraphConfig
from merino.utils.metrics import get_metrics_client


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
    sections_response_data, fixture_request_data, manifest_provider
):
    """Experiment suffixes should be parsed into a canonical section with an alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050"

    http_client = AsyncMock(spec=AsyncClient)
    http_client.post.return_value = Response(
        status_code=200,
        json=response_data,
        request=fixture_request_data,
    )
    backend = SectionsBackend(
        http_client=http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
    )

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government = next(section for section in sections if section.externalId == "government-test")
    assert government.experimentVariant == 0
    assert government.alternateSection is not None
    assert government.alternateSection.experimentVariant == 5050


@pytest.mark.asyncio
async def test_fetch_strips_locale_suffix_after_experiment_suffix(
    sections_response_data, fixture_request_data, manifest_provider
):
    """Locale stripping should preserve experiment metadata when linking the alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050__lDE_DE"

    http_client = AsyncMock(spec=AsyncClient)
    http_client.post.return_value = Response(
        status_code=200,
        json=response_data,
        request=fixture_request_data,
    )
    backend = SectionsBackend(
        http_client=http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
    )

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government = next(section for section in sections if section.externalId == "government-test")
    assert government.experimentVariant == 0
    assert government.alternateSection is not None
    assert government.alternateSection.experimentVariant == 5050


@pytest.mark.asyncio
async def test_fetch_links_experiment_variant_to_base_section(
    sections_response_data, fixture_request_data, manifest_provider
):
    """A base/variant pair should be returned as one canonical section with an alternate slate."""
    response_data = copy.deepcopy(sections_response_data)
    response_data["data"]["getSections"][0]["externalId"] = "government-test"
    response_data["data"]["getSections"][1]["externalId"] = "government-test__exp5050"

    http_client = AsyncMock(spec=AsyncClient)
    http_client.post.return_value = Response(
        status_code=200,
        json=response_data,
        request=fixture_request_data,
    )
    backend = SectionsBackend(
        http_client=http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
    )

    sections = await backend.fetch(SurfaceId.NEW_TAB_EN_US)

    government_sections = [
        section for section in sections if section.externalId == "government-test"
    ]
    assert len(government_sections) == 1
    assert government_sections[0].experimentVariant == 0
    assert government_sections[0].alternateSection is not None
    assert government_sections[0].alternateSection.experimentVariant == 5050
