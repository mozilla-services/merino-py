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
class SurfaceId(str, Enum):
    """Defines the possible recommendation surfaces."""

    NEW_TAB_EN_US = "NEW_TAB_EN_US"
    NEW_TAB_EN_GB = "NEW_TAB_EN_GB"
    NEW_TAB_EN_INTL = "NEW_TAB_EN_INTL"
    NEW_TAB_DE_DE = "NEW_TAB_DE_DE"
    NEW_TAB_ES_ES = "NEW_TAB_ES_ES"
    NEW_TAB_FR_FR = "NEW_TAB_FR_FR"
    NEW_TAB_IT_IT = "NEW_TAB_IT_IT"


class IABMetadata(BaseModel):
    """IAB (v3.0) metadata for a Section."""

    taxonomy: str  # IAB taxonomy v3.0 is currently used
    categories: list[str]


class CorpusItem(BaseModel):
    """Represents a scheduled item from our 'corpus'.
    The corpus is the set of all curated items deemed recommendable.
    """

    corpusItemId: str
    scheduledCorpusItemId: str | None = None
    url: HttpUrl
    title: str
    excerpt: str
    topic: Topic | None = None
    publisher: str
    isTimeSensitive: bool
    imageUrl: HttpUrl
    iconUrl: HttpUrl | None = None


class CorpusSection(BaseModel):
    """A list of section recommendations from the corpus API."""

    sectionItems: list[CorpusItem]
    title: str
    iab: IABMetadata | None = None
    externalId: str


class SectionsProtocol(Protocol):
    """Protocol for fetching sections of corpus items for a given surface, without a date."""

    async def fetch(self, surface_id: SurfaceId) -> list[CorpusSection]:
        """Fetch corpus items for the given surface.

        Args:
            surface_id: Identifies the scheduled surface, e.g. NEW_TAB_EN_US.

        Returns:
            list[CorpusSection]: A list of sections, each of which contains list of corpus items.
        """
        ...


class ScheduledSurfaceProtocol(Protocol):
    """Protocol for corpus backends extended with support for fetching items by day offset."""

    async def fetch(self, surface_id: SurfaceId, days_offset: int = 0) -> list[CorpusItem]:
        """Fetch corpus items for the given surface and day offset.

        Args:
            surface_id: Identifies the scheduled surface, e.g. NEW_TAB_EN_US.
            days_offset: Number of days relative to today (0 for today, negative for past, positive for future).

        Returns:
            list[CorpusItem]: A list of fetched corpus items.
        """
        ...
