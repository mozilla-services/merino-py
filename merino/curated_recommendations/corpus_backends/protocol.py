"""Protocol for the Corpus provider backend."""

from enum import Enum, unique
from typing import Protocol

from pydantic import BaseModel, HttpUrl


@unique
class Topic(str, Enum):
    """Topics supported for curated recommendations."""

    BUSINESS = "business"
    CAREER = "career"
    ARTS = "arts"
    FOOD = "food"
    HEALTH_FITNESS = "health"
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

    scheduledCorpusItemId: str
    url: HttpUrl
    title: str
    excerpt: str
    topic: Topic | None = None
    publisher: str
    imageUrl: HttpUrl


class CorpusBackend(Protocol):
    """Protocol for Curated Recommendation backend that the provider depends on."""

    async def fetch(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:  # pragma: no cover
        """Fetch Curated Recommendations"""
        ...
