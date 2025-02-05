"""Protocol for the Corpus provider backend."""

from enum import Enum, unique
from typing import Protocol

from pydantic import BaseModel, HttpUrl


@unique
class Topic(str, Enum):
    """Topics supported for curated recommendations.

    The section names must match the corresponding topic names in lowercase. Please update
    merino/curated_recommendations/protocol.py if the enum names (e.g. BUSINESS) are changed.

    The enum values correspond to the topic identifiers. Changing them would be a breaking change.
    """

    BUSINESS = "business"
    CAREER = "career"
    ARTS = "arts"
    FOOD = "food"
    HEALTH_FITNESS = "health"
    HOME = "home"
    PERSONAL_FINANCE = "finance"
    POLITICS = "government"
    SPORTS = "sports"
    TECHNOLOGY = "tech"
    TRAVEL = "travel"
    EDUCATION = "education"
    GAMING = "hobbies"
    PARENTING = "society-parenting"
    SCIENCE = "education-science"
    SELF_IMPROVEMENT = "society"


@unique
class ScheduledSurfaceId(str, Enum):
    """Defines the possible recommendation surfaces."""

    NEW_TAB_EN_US = "NEW_TAB_EN_US"
    NEW_TAB_EN_GB = "NEW_TAB_EN_GB"
    NEW_TAB_EN_INTL = "NEW_TAB_EN_INTL"
    NEW_TAB_DE_DE = "NEW_TAB_DE_DE"
    NEW_TAB_ES_ES = "NEW_TAB_ES_ES"
    NEW_TAB_FR_FR = "NEW_TAB_FR_FR"
    NEW_TAB_IT_IT = "NEW_TAB_IT_IT"


class CorpusItem(BaseModel):
    """Represents a scheduled item from our 'corpus'.
    The corpus is the set of all curated items deemed recommendable.
    """

    corpusItemId: str
    scheduledCorpusItemId: str
    url: HttpUrl
    title: str
    excerpt: str
    topic: Topic | None = None
    publisher: str
    isTimeSensitive: bool
    imageUrl: HttpUrl
    iconUrl: HttpUrl | None = None


class CorpusBackend(Protocol):
    """Protocol for Curated Recommendation backend that the provider depends on."""

    async def fetch(
        self,
        surface_id: ScheduledSurfaceId,
        days_offset: int = 0,
    ) -> list[CorpusItem]:
        """Fetch corpus items.

        Args:
            surface_id: Identifies the scheduled surface, for example NEW_TAB_EN_US.
            days_offset: Optionally, the number of days relative to today for which items were
                scheduled. A positive value indicates a future day, negative value indicates a past
                day, and 0 refers to today. Defaults to 0.

        Returns:
        list[CorpusItem]: A list of fetched corpus items.
        """
        ...
