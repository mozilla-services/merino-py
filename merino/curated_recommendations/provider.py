"""Provider for curated recommendations on New Tab."""

import time
from enum import Enum, unique

from pydantic import BaseModel

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
)


@unique
class TypeName(str, Enum):
    """This value could be used in the future to distinguish between different types of content.

    Currently, the only value is recommendation.
    """

    RECOMMENDATION = "recommendation"


@unique
class Locale(str, Enum):
    """Supported locales for curated recommendations on New Tab"""

    FR = ("fr",)
    FR_FR = ("fr-FR",)
    ES = ("es",)
    ES_ES = ("es-ES",)
    IT = ("it",)
    IT_IT = ("it-IT",)
    EN = ("en",)
    EN_CA = ("en-CA",)
    EN_GB = ("en-GB",)
    EN_US = ("en-US",)
    DE = ("de",)
    DE_DE = ("de-DE",)
    DE_AT = ("de-AT",)
    DE_CH = ("de-CH",)


class CuratedRecommendation(CorpusItem):
    """Extends CorpusItem with additional fields for a curated recommendation"""

    __typename: TypeName = TypeName.RECOMMENDATION
    receivedRank: int


class CuratedRecommendationsRequest(BaseModel):
    """Body schema for requesting a list of curated recommendations"""

    locale: Locale
    region: str | None = None
    count: int = 100


class CuratedRecommendationsResponse(BaseModel):
    """Response schema for a list of curated recommendations"""

    recommendedAt: int
    data: list[CuratedRecommendation]


class CuratedRecommendationsProvider:
    """Provider for recommendations that have been reviewed by human curators."""

    corpus_backend: CorpusBackend

    def __init__(
        self,
        corpus_backend: CorpusBackend,
    ) -> None:
        self.corpus_backend = corpus_backend

    async def fetch(self) -> CuratedRecommendationsResponse:
        """Provide curated recommendations."""
        corpus_items = await self.corpus_backend.fetch()

        # Convert the CorpusItem list to a CuratedRecommendation list.
        recommendations = [
            CuratedRecommendation(
                **item.model_dump(),
                receivedRank=rank,
            )
            for rank, item in enumerate(corpus_items)
        ]

        return CuratedRecommendationsResponse(
            recommendedAt=self.time_ms(),
            data=recommendations,
        )

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)