"""Tests covering merino/curated_recommendations/corpus_backends/sections_corpus_backend.py"""

import pytest

from merino.curated_recommendations import SectionsCorpusBackend
from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId


@pytest.mark.asyncio
async def test_fetch(sections_backend: SectionsCorpusBackend):
    """Test that fetch returns expected sections from the backend."""
    sections = await sections_backend.fetch(ScheduledSurfaceId.NEW_TAB_EN_US)
    assert isinstance(sections, list)

    # Lookup the Health section by its externalId.
    health = next(s for s in sections if s.externalId == "cvb-345")
    assert health.title == "Health"
    assert len(health.sectionItems) == 0

    # Lookup the Music section by its externalId.
    music = next(s for s in sections if s.externalId == "music")
    assert music is not None
    assert music.title == "Music"
    assert len(music.sectionItems) == 25
