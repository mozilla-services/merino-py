"""TODO"""

from typing import Any
from pydantic import Field, BaseModel, HttpUrl
from merino.curated_recommendations.protocol import Locale

LEGACY_FX114_RECS_SETTINGS = {
    "domainAffinityParameterSets": {},
    "timeSegments": [
        {
            "id": "week",
            "startTime": 604800,
            "endTime": 0,
            "weightPosition": 1,
        },
        {
            "id": "month",
            "startTime": 2592000,
            "endTime": 604800,
            "weightPosition": 0.5,
        },
    ],
    "recsExpireTime": 5400,
    "spocsPerNewTabs": 0.5,
    "version": "6f605b0212069b4b8d3d040faf55742061a25c16",
}


class CuratedRecommendationsLegacyFx115fx129Request(BaseModel):
    """Request query parameters/variables received for
    the /curated-recommendations/legacy-115-129 endpoint
    """

    locale: Locale
    region: str | None = None
    count: int = 30


class CuratedRecommendationsLegacyFx114Request(BaseModel):
    """Request query parameters/variables received for
    the /curated-recommendations/legacy-global-recs-114 endpoint
    """

    locale_lang: Locale
    region: str | None = None
    count: int = 10


class CuratedRecommendationLegacyFx115Fx129(BaseModel):
    """Schema for a single desktop legacy recommendation."""

    # Note we can't name this variable as `__typename`
    # because it is then considered an internal variable by Pydantic and omitted in the final API response.
    typename: str = Field(default="Recommendation", alias="__typename")
    recommendationId: str
    tileId: int
    url: HttpUrl
    title: str
    excerpt: str
    publisher: str
    imageUrl: HttpUrl

    class Config:
        """Allow field population using aliases (e.g., __typename)"""

        populate_by_name = True


class CuratedRecommendationLegacyFx114(BaseModel):
    """Schema for a single legacy global recommendation."""

    id: int
    title: str
    url: HttpUrl
    excerpt: str
    domain: str
    image_src: HttpUrl
    raw_image_src: HttpUrl


class CuratedRecommendationsLegacyFx115Fx129Response(BaseModel):
    """Response schema for a list of curated recommendations for
    the /curated-recommendations/legacy-115-129 endpoint
    """

    data: list[CuratedRecommendationLegacyFx115Fx129]


class CuratedRecommendationsLegacyFx114Response(BaseModel):
    """Response schema for a list of curated recommendations for
    /curated-recommendations/legacy-global-recs-114 endpoint
    """

    status: int = 1
    spocs: list = Field(default_factory=list)
    settings: dict[str, Any] = LEGACY_FX114_RECS_SETTINGS
    recommendations: list[CuratedRecommendationLegacyFx114]
