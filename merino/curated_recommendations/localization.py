"""Hardcoded localized strings."""

# Hardcoded localized topic section titles (for now) for en-US & de-DE
from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId

LocalizedTopicSectionTitles = dict[ScheduledSurfaceId, dict[str, str]]

LOCALIZED_TOPIC_SECTION_TITLES: LocalizedTopicSectionTitles = {
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
        "top-stories": "Heute Beliebt",
    },
}
