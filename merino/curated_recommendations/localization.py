"""Hardcoded localized strings."""

from datetime import datetime

from babel.dates import format_date

from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId
import logging

logger = logging.getLogger(__name__)


LocalizedTopicSectionTitles = dict[ScheduledSurfaceId, dict[str, str]]

# Hardcoded localized topic section titles (for now) for en-US & de-DE
LOCALIZED_SECTION_TITLES: LocalizedTopicSectionTitles = {
    # reference: https://searchfox.org/mozilla-central/source/browser/locales/en-US/browser/newtab/newtab.ftl#392
    ScheduledSurfaceId.NEW_TAB_EN_US: {
        "business": "Business",
        "career": "Career",
        "education": "Education",
        "arts": "Entertainment",
        "food": "Food",
        "health": "Health",
        "hobbies": "Gaming",
        "finance": "Money",
        "society-parenting": "Parenting",
        "government": "Politics",
        "education-science": "Science",
        "society": "Life Hacks",
        "sports": "Sports",
        "tech": "Tech",
        "travel": "Travel",
        "home": "Home & Garden",
        "top-stories": "Popular Today",
        "news-section": "In the News",
    },
    # reference: https://github.com/mozilla-l10n/firefox-l10n/blob/main/de/browser/browser/newtab/newtab.ftl#L407
    ScheduledSurfaceId.NEW_TAB_DE_DE: {
        "business": "Geschäftliches",
        "career": "Karriere",
        "education": "Bildung",
        "arts": "Unterhaltung",
        "food": "Essen",
        "health": "Gesundheit",
        "hobbies": "Gaming",
        "finance": "Finanzen",
        "society-parenting": "Erziehung",
        "government": "Politik",
        "education-science": "Wissenschaft",
        "society": "Life-Hacks",
        "sports": "Sport",
        "tech": "Technik",
        "travel": "Reisen",
        "home": "Haus und Garten",
        "top-stories": "Meistgelesen",
        "news-section": "In den News",
    },
}


def get_translation(surface_id: ScheduledSurfaceId, topic: str, default_topic: str) -> str:
    """Retrieve a translation and log an error if a translation doesn't exist."""
    if surface_id not in LOCALIZED_SECTION_TITLES:
        logger.error(
            f"No translations found for surface '{surface_id}'. Defaulting to topic: '{default_topic}'"
        )
        return default_topic

    translations = LOCALIZED_SECTION_TITLES.get(surface_id, {})
    if topic not in translations or not translations[topic]:
        logger.error(
            f"Missing or empty translation for topic '{topic}' for surface '{surface_id}'. "
            f"Defaulting to topic: '{default_topic}'"
        )
        return default_topic

    return translations[topic]


# Localization for Babel date formats based on surface_id.
SURFACE_ID_TO_LOCALE = {
    ScheduledSurfaceId.NEW_TAB_EN_US: "en_US",
    ScheduledSurfaceId.NEW_TAB_EN_GB: "en_GB",
    ScheduledSurfaceId.NEW_TAB_DE_DE: "de_DE",
    ScheduledSurfaceId.NEW_TAB_FR_FR: "fr_FR",
    ScheduledSurfaceId.NEW_TAB_ES_ES: "es_ES",
    ScheduledSurfaceId.NEW_TAB_IT_IT: "it_IT",
    ScheduledSurfaceId.NEW_TAB_EN_INTL: "en_IN",  # En-Intl is primarily used in India.
}


def get_localized_date(surface_id: ScheduledSurfaceId, date: datetime) -> str:
    """Return a localized date string for the given ScheduledSurfaceId.

    Args:
        surface_id (ScheduledSurfaceId): The New Tab surface ID.
        date (datetime): The date to be localized.

    Returns:
        str: Localized date string, for example "December 17, 2024".
    """
    return format_date(date, format="long", locale=SURFACE_ID_TO_LOCALE.get(surface_id, "en_US"))
