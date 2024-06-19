"""Protocol for the Corpus provider backend."""
from enum import Enum, unique
from typing import Protocol

from pydantic import BaseModel, HttpUrl


@unique
class Topic(str, Enum):
    ARTS = ("arts",)
    BUSINESS = ("business",)
    EDUCATION = ("education",)
    FINANCE = ("finance",)
    FOOD = ("food",)
    GOVERNMENT = ("government",)
    HEALTH = ("health",)
    SOCIETY = ("society",)
    SPORTS = ("sports",)
    TECH = ("tech",)
    TRAVEL = ("travel",)

    @staticmethod
    def values():
        """maps enum values & returns"""
        return Topic._value2member_map_


class CorpusItem(BaseModel):
    scheduledCorpusItemId: str
    url: HttpUrl
    title: str
    excerpt: str
    topic: Topic | None = None
    publisher: str
    imageUrl: HttpUrl


class CorpusBackend(Protocol):
    """Protocol for Curated Recommendation backend that the provider depends on."""

    async def fetch(self) -> list[CorpusItem]:  # pragma: no cover
        """Fetch Curated Recommendations

        Raises:
            BackendError: If curated recommendations are unavailable.
        """
        ...
