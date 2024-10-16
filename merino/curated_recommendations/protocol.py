"""Curated Recommendations provider top-level request and response models"""

import hashlib
from enum import unique, Enum
from typing import Annotated
import logging

from pydantic import Field, field_validator, model_validator, BaseModel, HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, Topic

logger = logging.getLogger(__name__)


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

    @staticmethod
    def values():
        """Map enum values & returns"""
        return Locale._value2member_map_


@unique
class ExperimentName(str, Enum):
    """List of Nimbus experiment names on New Tab. This list is NOT meant to be exhaustive.
    This is simply intended to make it easier to reference experiment names in this codebase,
    when Merino needs to change behavior depending on the experimentName request parameter.
    """

    REGION_SPECIFIC_CONTENT_EXPANSION = "new-tab-region-specific-content-expansion"


# Maximum tileId that Firefox can support. Firefox uses Javascript to store this value. The max
# value of a Javascript number can be found using `Number.MAX_SAFE_INTEGER`. which is 2^53 - 1
# because it uses a 64-bit IEEE 754 float.
# Generate tile_ids well out of the range of the old MySQL-based system, which has a max tile_id of
# 99,999 as of 2023-03-13. This is done to make it easy for engineers/analysts to see which system
# generated the identifier.
MAX_TILE_ID = (1 << 53) - 1
MIN_TILE_ID = 10000000


class CuratedRecommendation(CorpusItem):
    """Extends CorpusItem with additional fields for a curated recommendation"""

    __typename: TypeName = TypeName.RECOMMENDATION
    tileId: Annotated[int, Field(strict=True, ge=MIN_TILE_ID, le=MAX_TILE_ID)]
    receivedRank: int

    @model_validator(mode="before")
    def set_tileId(cls, values):
        """Set the tileId field automatically."""
        scheduled_corpus_item_id = values.get("scheduledCorpusItemId")

        if scheduled_corpus_item_id and "tileId" not in values:
            values["tileId"] = cls._integer_hash(
                scheduled_corpus_item_id, MIN_TILE_ID, MAX_TILE_ID
            )

        return values

    @staticmethod
    def _integer_hash(s: str, start: int, stop: int) -> int:
        """:param s: String to be hashed.
        :param start: Minimum integer to be returned.
        :param stop: Integer that is greater than start. Maximum return value is stop - 1.
        :return: Integer hash of s in the range [start, stop)
        """
        return start + (int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16) % (stop - start))


class CuratedRecommendationsRequest(BaseModel):
    """Body schema for requesting a list of curated recommendations"""

    locale: Locale
    region: str | None = None
    count: int = 100
    topics: list[Topic | str] | None = None
    feeds: list[str] | None = None
    # Firefox sends the name and branch for Nimbus experiments on the "pocketNewtab" feature:
    # https://searchfox.org/mozilla-central/source/browser/components/newtab/lib/DiscoveryStreamFeed.sys.mjs
    # Allow any string value or null, because ExperimentName is not meant to be an exhaustive list.
    experimentName: ExperimentName | str | None = None
    experimentBranch: str | None = None

    @field_validator("topics", mode="before")
    def validate_topics(cls, values):
        """Validate the topics param."""
        if values:
            if isinstance(values, list):
                valid_topics = []
                for value in values:
                    # if value is a valid Topic, add it to valid_topics
                    if isinstance(value, Topic):
                        valid_topics.append(value)
                    # if value is a string, check if its in enum Topic
                    # skip if invalid topic
                    elif isinstance(value, str):
                        try:
                            valid_topics.append(Topic(value))
                        except ValueError:
                            # Skip invalid topics
                            logger.warning(f"Invalid topic: {value}")
                            continue
                return valid_topics
            else:
                # Not wrapped in a list
                logger.warning(f"Topics not wrapped in a list: {values}")
        return []


# Fakespot header/footer cta copy hardcoded strings for now.
FAKESPOT_HEADER_COPY = "Fakespot by Mozilla curates the chaos of online shopping into gift guides you can trust."
FAKESPOT_FOOTER_COPY = "Take the guesswork out of gifting with the Fakespot Gift Guide."
FAKESPOT_CTA_COPY = "Explore More Gifts"
FAKESPOT_CTA_URL = "https://fakespot-gifts.com/"


class FakespotProduct(BaseModel):
    """Fakespot product details"""

    title: str
    imageUrl: HttpUrl
    url: HttpUrl


class FakespotProductCategory(BaseModel):
    """Fakespot product category details"""

    name: str
    products: list[FakespotProduct]


class FakespotCTA(BaseModel):
    copy: str
    url: HttpUrl


class FakespotFeed(BaseModel):
    """Fakespot product recommendations"""

    categories: list[FakespotProductCategory]
    headerCopy: str
    footerCopy: str
    cta: FakespotCTA


class CuratedRecommendationsBucket(BaseModel):
    """A ranked list of curated recommendations"""

    recommendations: list[CuratedRecommendation]
    title: str | None = None


class CuratedRecommendationsFeed(BaseModel):
    """Multiple lists of curated recommendations for experiments.
    Currently limited to the 'need_to_know' & fakespot feed only.
    """

    need_to_know: CuratedRecommendationsBucket | None = None
    fakespot: FakespotFeed | None = None


class CuratedRecommendationsResponse(BaseModel):
    """Response schema for a list of curated recommendations"""

    recommendedAt: int
    data: list[CuratedRecommendation]
    feeds: CuratedRecommendationsFeed | None = None
