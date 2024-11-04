"""Curated Recommendations provider top-level request and response models"""

import hashlib
from enum import unique, Enum
from typing import Annotated
import logging

from pydantic import Field, field_validator, model_validator, BaseModel

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, Topic
from merino.curated_recommendations.fakespot_backend.protocol import FakespotFeed

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

    # Experiment where large countries receive region-specific ranking.
    REGION_SPECIFIC_CONTENT_EXPANSION = "new-tab-region-specific-content-expansion"
    # Same as the above, but targeting small countries, which need a higher enrollment %.
    REGION_SPECIFIC_CONTENT_EXPANSION_SMALL = "new-tab-region-specific-content-expansion-small"
    # Experiment where high-engaging items scheduled for past dates are included.
    EXTENDED_EXPIRATION_EXPERIMENT = "new-tab-extended-expiration-experiment"


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


class CuratedRecommendationsBucket(BaseModel):
    """A ranked list of curated recommendations"""

    recommendations: list[CuratedRecommendation]
    title: str | None = None


class Section(BaseModel):
    """A ranked list of curated recommendations"""

    receivedRank: int
    recommendations: list[CuratedRecommendation]
    title: str
    subtitle: str | None = None


class CuratedRecommendationsFeed(BaseModel):
    """Multiple lists of curated recommendations, that are currently in an experimental phase."""

    need_to_know: CuratedRecommendationsBucket | None = None
    fakespot: FakespotFeed | None = None

    # The following feeds are used as mock data for the 'sections' experiment.
    # They should be removed when the sections are implemented that we'll actually launch with.
    business: Section | None = None
    career: Section | None = None
    arts: Section | None = None
    food: Section | None = None
    health_fitness: Section | None = None
    home: Section | None = None
    personal_finance: Section | None = None
    politics: Section | None = None
    sports: Section | None = None
    technology: Section | None = None
    travel: Section | None = None
    education: Section | None = None
    gaming: Section | None = None
    parenting: Section | None = None
    science: Section | None = None
    self_improvement: Section | None = None
    top_stories_section: Section | None = None


class CuratedRecommendationsResponse(BaseModel):
    """Response schema for a list of curated recommendations"""

    recommendedAt: int
    data: list[CuratedRecommendation]
    feeds: CuratedRecommendationsFeed | None = None
