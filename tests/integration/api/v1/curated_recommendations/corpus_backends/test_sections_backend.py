"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import pytest

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)
    # The test data now includes both regular sections and _crawl versions
    assert len(sections) == 43

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
