"""Hardcoded localized strings."""

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
import logging

logger = logging.getLogger(__name__)


LocalizedTopicSectionTitles = dict[SurfaceId, dict[str, str]]

# Hardcoded localized topic section titles (for now) for en-US & de-DE
LOCALIZED_SECTION_TITLES: LocalizedTopicSectionTitles = {
    # reference: https://searchfox.org/mozilla-central/source/browser/locales/en-US/browser/newtab/newtab.ftl#392
    SurfaceId.NEW_TAB_EN_US: {
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
    },
    # reference: https://github.com/mozilla-l10n/firefox-l10n/blob/main/de/browser/browser/newtab/newtab.ftl#L407
    SurfaceId.NEW_TAB_DE_DE: {
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
    },
}


def get_translation(surface_id: SurfaceId, topic: str, default_topic: str) -> str:
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
