"""Provider for curated recommendations on New Tab."""

import hashlib
import time
import re

from copy import copy
from enum import Enum, unique
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    ScheduledSurfaceId,
    Topic,
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

    @staticmethod
    def values():
        """Map enum values & returns"""
        return Locale._value2member_map_


# Maximum tileId that Firefox can support. Firefox uses Javascript to store this value. The max
# value of a Javascript number can be found using `Number.MAX_SAFE_INTEGER`. which is 2^53 - 1
# because it uses a 64-bit IEEE 754 float.
MAX_TILE_ID = (1 << 53) - 1
# Generate tile_ids well out of the range of the old MySQL-based system, which has a max tile_id of
# 99,999 as of 2023-03-13. This is done to make it easy for engineers/analysts to see which system
# generated the identifier.
MIN_TILE_ID = 10000000

NUM_RECS_PER_TOPIC = 2
MAX_TOP_REC_SLOTS = 10


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
    topics: list[Topic] | None = None


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

    @staticmethod
    def get_recommendation_surface_id(
        locale: Locale, region: str | None = None
    ) -> ScheduledSurfaceId:
        """Locale/region mapping is documented here:
        https://docs.google.com/document/d/1omclr-eETJ7zAWTMI7mvvsc3_-ns2Iiho4jPEfrmZfo/edit

        Args:
            locale: The language variant preferred by the user (e.g. 'en-US', or 'en')
            region: Optionally, the geographic region of the user, e.g. 'US'.

        Return the most appropriate RecommendationSurfaceId for the given locale/region.
        A value is always returned here. A Firefox pref determines which locales are eligible, so in this
        function call we can assume that the locale/region has been deemed suitable to receive NewTab recs.
        Ref: https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/app/data_providers/dispatch.py#L416 # noqa
        """
        language = CuratedRecommendationsProvider.extract_language_from_locale(locale)
        derived_region = CuratedRecommendationsProvider.derive_region(locale, region)

        if language == "de":
            return ScheduledSurfaceId.NEW_TAB_DE_DE
        elif language == "es":
            return ScheduledSurfaceId.NEW_TAB_ES_ES
        elif language == "fr":
            return ScheduledSurfaceId.NEW_TAB_FR_FR
        elif language == "it":
            return ScheduledSurfaceId.NEW_TAB_IT_IT
        else:
            # Default to English language for all other values of language (including 'en' or None)
            if derived_region is None or derived_region in ["US", "CA"]:
                return ScheduledSurfaceId.NEW_TAB_EN_US
            elif derived_region in ["GB", "IE"]:
                return ScheduledSurfaceId.NEW_TAB_EN_GB
            elif derived_region in ["IN"]:
                return ScheduledSurfaceId.NEW_TAB_EN_INTL
            else:
                # Default to the en-US New Tab if no 2-letter region can be derived from locale or region.
                return ScheduledSurfaceId.NEW_TAB_EN_US

    @staticmethod
    def extract_language_from_locale(locale: Locale) -> str | None:
        """Return a 2-letter language code from a locale string like 'en-US' or 'en'.
        Ref: https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/app/data_providers/dispatch.py#L451 # noqa
        """
        match = re.search(r"[a-zA-Z]{2}", locale)
        if match:
            return match.group().lower()
        else:
            return None

    @staticmethod
    def derive_region(locale: Locale, region: str | None = None) -> str | None:
        """Derive the region from the `region` argument if provided, otherwise try to extract from the locale.

        Args:
             locale: The language-variant preferred by the user (e.g. 'en-US' means English-as-spoken in the US)
             region: Optionally, the geographic region of the user, e.g. 'US'.

        Return a 2-letter region like 'US'.
        Ref: https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/app/data_providers/dispatch.py#L451 # noqa
        """
        # Derive from provided region
        if region:
            m1 = re.search(r"[a-zA-Z]{2}", region)
            if m1:
                return m1.group().upper()
        # If region not provided, derive from locale
        m2 = re.search(r"[_\-]([a-zA-Z]{2})", locale)
        if m2:
            return m2.group(1).upper()
        else:
            return None

    @staticmethod
    def spread_publishers(
        recs: list[CuratedRecommendation], spread_distance: int
    ) -> list[CuratedRecommendation]:
        """Spread a list of CuratedRecommendations by the publisher attribute to avoid encountering the same publisher
        in sequence.

        :param recs: The recommendations to be spread
        :param spread_distance: The distance that recs with the same publisher value should be spread apart. The default
            value of None greedily maximizes the distance, by basing the spread distance on the number of unique values.
        :return: CuratedRecommendations spread by publisher, while otherwise preserving the order.
        """
        attr = "publisher"

        result_recs: list[CuratedRecommendation] = []
        remaining_recs = copy(recs)

        while remaining_recs:
            values_to_avoid = set(getattr(r, attr) for r in result_recs[-spread_distance:])
            # Get the first remaining rec which value should not be avoided, or default to the first remaining rec.
            rec = next(
                (r for r in remaining_recs if getattr(r, attr) not in values_to_avoid),
                remaining_recs[0],
            )
            result_recs.append(rec)
            remaining_recs.remove(rec)

        return result_recs

    @staticmethod
    def get_top_recommendations_by_topic(
        recs: list[CuratedRecommendation],
        preferred_topics: list[Topic],
        max_top_recs: int = MAX_TOP_REC_SLOTS,
    ) -> list[CuratedRecommendation]:
        """Get top recommendations based on preferred topics. 2 recs per preferred topic.

        :param recs: List of recs to filter and boost
        :param preferred_topics: User's preferred topic(s)
        :param max_top_recs: Max number of top recs to return based on preferred topics in the first N slots.
                             Default is 10.
        :return: List of reordered recs based on preferred topics
        """
        # dictionary to store recommendations by preferred topic
        topic_dict: dict[Topic, list[CuratedRecommendation]] = {
            topic: [] for topic in preferred_topics
        }

        # group by topic
        for rec in recs:
            if rec.topic in topic_dict:
                topic_dict[rec.topic].append(rec)

        # Get the number of top recommendations based on the number of preferred topics
        # i.e., 2 topics = 4 recs, 3 topics = 6 recs, etc. Max top recs is 10.
        top_recs = []

        for topic in preferred_topics:
            top_recs.extend(topic_dict.get(topic, [])[:NUM_RECS_PER_TOPIC])

        # Limit the total number of top recommendations (10 is max for now)
        return top_recs[:max_top_recs]

    @staticmethod
    def is_boostable(
        recs: list[CuratedRecommendation],
        preferred_topics: list[Topic],
    ) -> bool:
        """Check if top N recommendations need boosting based on preferred topics.

        :param recs: List of recommendations
        :param preferred_topics: User's preferred topic(s)
        :return: True if boosting is needed (i.e. less than 2 stories per topic in top N slots), else False
        """
        num_topics = len(preferred_topics)

        if num_topics >= 5:
            num_top_recs = MAX_TOP_REC_SLOTS
        else:
            num_top_recs = num_topics * NUM_RECS_PER_TOPIC

        top_recs = recs[:num_top_recs]

        # Create a dictionary to track how many stories per topic are in the top N slots
        # Start with 0
        topic_count = {topic: 0 for topic in preferred_topics}

        for rec in top_recs:
            if rec.topic in topic_count:
                topic_count[rec.topic] += 1

        # Check if each topic has at least 2 stories in the top N slots
        return any(rec_count < NUM_RECS_PER_TOPIC for rec_count in topic_count.values())

    @staticmethod
    def boost_preferred_topic(
        recs: list[CuratedRecommendation],
        preferred_topics: list[Topic],
    ) -> list[CuratedRecommendation]:
        """Boost recommendations into top N slots based on preferred topics.

        :param recs: List of recommendations
        :param preferred_topics: User's preferred topic(s)
        :return: CuratedRecommendations ranked based on a preferred topic(s), while otherwise preserving the order.
        """
        # Get the top recommendations based on preferred topics
        top_recs = CuratedRecommendationsProvider.get_top_recommendations_by_topic(
            recs, preferred_topics
        )

        # Create a shallow copy of recs
        recs = recs.copy()

        # Remove top_recs from the original list if they exist
        for boostable_rec in top_recs:
            if boostable_rec in recs:
                recs.remove(boostable_rec)

        # Insert top_recs into the start of the list
        recs = top_recs + recs

        return recs

    async def fetch(
        self, curated_recommendations_request: CuratedRecommendationsRequest
    ) -> CuratedRecommendationsResponse:  # noqa
        """Provide curated recommendations."""
        # Get the recommendation surface ID based on passed locale & region
        surface_id = CuratedRecommendationsProvider.get_recommendation_surface_id(
            curated_recommendations_request.locale, curated_recommendations_request.region
        )

        corpus_items = await self.corpus_backend.fetch(surface_id)

        # Convert the CorpusItem list to a CuratedRecommendation list.
        recommendations = [
            CuratedRecommendation(
                **item.model_dump(),
                receivedRank=rank,
            )
            for rank, item in enumerate(corpus_items)
        ]

        # 2. Perform publisher spread on the recommendation set
        recommendations = self.spread_publishers(recommendations, spread_distance=3)

        # 1. Finally, perform preferred topics boosting if preferred topics are passed in the request
        if curated_recommendations_request.topics:
            # Check if recs need boosting
            if self.is_boostable(recommendations, curated_recommendations_request.topics):
                recommendations = self.boost_preferred_topic(
                    recommendations, curated_recommendations_request.topics
                )

        return CuratedRecommendationsResponse(
            recommendedAt=self.time_ms(),
            data=recommendations,
        )

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)
