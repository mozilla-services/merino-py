"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import pytest

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)
    # The test data includes both regular sections and _crawl versions
    # Check that we have at least 10 sections with _crawl suffix
    crawl_sections = [s for s in sections if s.externalId.endswith("_crawl")]
    assert (
        len(crawl_sections) >= 10
    ), f"Expected at least 10 _crawl sections, got {len(crawl_sections)}"

    # Check that we have at least 10 sections without _crawl suffix
    non_crawl_sections = [s for s in sections if not s.externalId.endswith("_crawl")]
    assert (
        len(non_crawl_sections) >= 10
    ), f"Expected at least 10 non-_crawl sections, got {len(non_crawl_sections)}"

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
    headlines = next(s for s in sections if s.externalId == "headlines_crawl")
    assert headlines is not None
    assert headlines.title == "Headlines"
    assert headlines.description == "Top Headlines today"
