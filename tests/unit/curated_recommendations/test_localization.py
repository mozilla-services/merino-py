"""Tests covering merino/curated_recommendations/localization.py"""

from datetime import datetime

import pytest

from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId
from merino.curated_recommendations.localization import get_translation, get_localized_date


def test_get_translation_existing_translation():
    """Test that get_translation returns existing translations."""
    result = get_translation(ScheduledSurfaceId.NEW_TAB_EN_US, "business", "Default")
    assert result == "Business"


def test_get_translation_non_existing_locale(caplog):
    """Test logs error and falls back to default when locale translations do not exist."""
    result = get_translation(ScheduledSurfaceId.NEW_TAB_IT_IT, "business", "Default")
    assert result == "Default"

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "No translations found for surface" in errors[0].message


def test_get_translation_non_existing_slug(caplog):
    """Test logs error and falls back to default when the topic slug does not exist."""
    result = get_translation(ScheduledSurfaceId.NEW_TAB_EN_US, "non_existing_slug", "Default")
    assert result == "Default"

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "Missing or empty translation for topic" in errors[0].message


@pytest.mark.parametrize(
    "surface_id, expected_output",
    [
        (ScheduledSurfaceId.NEW_TAB_EN_US, "December 17, 2024"),
        (ScheduledSurfaceId.NEW_TAB_EN_GB, "17 December 2024"),
        (ScheduledSurfaceId.NEW_TAB_DE_DE, "17. Dezember 2024"),
        (ScheduledSurfaceId.NEW_TAB_FR_FR, "17 décembre 2024"),
        (ScheduledSurfaceId.NEW_TAB_ES_ES, "17 de diciembre de 2024"),
        (ScheduledSurfaceId.NEW_TAB_IT_IT, "17 dicembre 2024"),
        (ScheduledSurfaceId.NEW_TAB_EN_INTL, "17 December 2024"),
    ],
)
def test_get_localized_date_output(surface_id: ScheduledSurfaceId, expected_output: str):
    """Test that get_localized_date returns correctly formatted date strings."""
    assert get_localized_date(surface_id, date=datetime(2024, 12, 17)) == expected_output
