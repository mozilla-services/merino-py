"""Tests covering merino/curated_recommendations/localization.py"""

from merino.curated_recommendations.localization import get_translation
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId


def test_get_translation_existing_translation():
    """Test that get_translation returns existing translations."""
    result = get_translation(SurfaceId.NEW_TAB_EN_US, "top-stories", "Default")
    assert result == "Popular Today"


def test_get_translation_en_ca():
    """Test that en-CA surface has correct localized section title."""
    result = get_translation(SurfaceId.NEW_TAB_EN_CA, "top-stories", "Default")
    assert result == "Popular Today"


def test_get_translation_non_existing_locale(caplog):
    """Test logs error and falls back to default when locale translations do not exist."""
    result = get_translation(SurfaceId.NEW_TAB_IT_IT, "business", "Default")
    assert result == "Default"

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "No translations found for surface" in errors[0].message


def test_get_translation_non_existing_slug(caplog):
    """Test logs error and falls back to default when the topic slug does not exist."""
    result = get_translation(SurfaceId.NEW_TAB_EN_US, "non_existing_slug", "Default")
    assert result == "Default"

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "Missing or empty translation for topic" in errors[0].message
