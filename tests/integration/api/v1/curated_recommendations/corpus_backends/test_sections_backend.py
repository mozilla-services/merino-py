"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import pytest

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.protocol import CreateSource, SurfaceId


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)
    # We no longer expect crawl sections from fixtures.
    assert all(
        not section.externalId.endswith("_crawl") for section in sections
    ), "Fixture should not contain crawl sections"
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
