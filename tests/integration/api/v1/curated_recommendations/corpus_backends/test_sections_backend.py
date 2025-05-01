"""Tests covering merino/curated_recommendations/corpus_backends/sections_backend.py"""

import pytest

from merino.curated_recommendations import SectionsBackend
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(SurfaceId.NEW_TAB_EN_US)
    assert len(sections) == 8

    # Lookup the NFL section by its externalId.
    hfl = next(s for s in sections if s.externalId == "nfl")
    assert hfl.title == "NFL"
    assert len(hfl.sectionItems) == 24

    # Lookup the Music section by its externalId.
    music = next(s for s in sections if s.externalId == "music")
    assert music is not None
    assert music.title == "Music"
    assert len(music.sectionItems) == 18
