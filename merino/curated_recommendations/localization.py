"""Hardcoded localized strings."""

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
import logging

logger = logging.getLogger(__name__)


LocalizedTopicSectionTitles = dict[SurfaceId, dict[str, str]]

# Hardcoded localized section titles. Only "top-stories" is used; other section
# titles come from the backend API (corpus_section.title).
# This dict also acts as a gating mechanism - only surfaces listed here can
# receive sections.
LOCALIZED_SECTION_TITLES: LocalizedTopicSectionTitles = {
    SurfaceId.NEW_TAB_EN_US: {
        "top-stories": "Popular Today",
    },
    SurfaceId.NEW_TAB_EN_GB: {
        "top-stories": "Popular Today",
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
