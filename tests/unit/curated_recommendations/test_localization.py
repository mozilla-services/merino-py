"""Tests covering merino/curated_recommendations/localization.py"""

import pytest

from merino.curated_recommendations.localization import get_translation
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId


@pytest.mark.parametrize(
    ("surface_id", "expected_title"),
    [
        (SurfaceId.NEW_TAB_EN_US, "Popular Today"),
        (SurfaceId.NEW_TAB_EN_CA, "Popular Today"),
        (SurfaceId.NEW_TAB_EN_IE, "Popular Today"),
        (SurfaceId.NEW_TAB_EN_XE, "Popular Today"),
        (SurfaceId.NEW_TAB_DE_DE, "Meistgelesen"),
        (SurfaceId.NEW_TAB_ES_XA, "Tendencias"),
        (SurfaceId.NEW_TAB_FR_FR, "Tendances du jour"),
        (SurfaceId.NEW_TAB_PL_PL, "Przegląd dnia"),
        (SurfaceId.NEW_TAB_ES_ES, "Tendencias"),
        (SurfaceId.NEW_TAB_IT_IT, "I più letti"),
    ],
    ids=["en_us", "en_ca", "en_ie", "en_xe", "de_de", "es_xa", "fr_fr", "pl_pl", "es_es", "it_it"],
)
def test_get_translation_top_stories(surface_id: SurfaceId, expected_title: str):
    """Test that each supported surface returns its localized top-stories title."""
    result = get_translation(surface_id, "top-stories", "Default")
    assert result == expected_title


def test_get_translation_non_existing_locale(caplog):
    """Test logs error and falls back to default when locale translations do not exist."""
    result = get_translation(SurfaceId.NEW_TAB_EN_INTL, "business", "Default")
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
