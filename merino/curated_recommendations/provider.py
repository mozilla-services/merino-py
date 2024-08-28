"""Provider for curated recommendations on New Tab."""

import time
import re

from copy import copy

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    ScheduledSurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.protocol import (
    Locale,
    CuratedRecommendation,
    CuratedRecommendationsRequest,
    CuratedRecommendationsResponse,
)
from merino.curated_recommendations.rankers import thompson_sampling


class CuratedRecommendationsProvider:
    """Provider for recommendations that have been reviewed by human curators."""

    corpus_backend: CorpusBackend

    def __init__(
        self, corpus_backend: CorpusBackend, engagement_backend: EngagementBackend
    ) -> None:
        self.corpus_backend = corpus_backend
        self.engagement_backend = engagement_backend

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
        # derive from provided region
        if region:
            m1 = re.search(r"[a-zA-Z]{2}", region)
            if m1:
                return m1.group().upper()
        # if region not provided, derive from locale
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
    def is_boostable(
        recs: list[CuratedRecommendation], preferred_topics: list[Topic], num_of_recs: int = 2
    ) -> bool:
        """Check if top 2 recommendations already have the preferred topics.
        This will indicate if recs need boosting.

        :param recs: List of recommendations
        :param preferred_topics: user's preferred topic(s)
        :param num_of_recs: get the first num of recs when slicing
        :return: bool
        """
        top_two_recs = recs[:num_of_recs]  # slice operator, get the first two recs (index 0 & 1)
        # check if topics in first two (0-1 index) recs are in preferred_topics
        if not any(r.topic in preferred_topics for r in top_two_recs):
            return True
        return False

    @staticmethod
    def boost_preferred_topic(
        recs: list[CuratedRecommendation],
        preferred_topics: list[Topic],
        boostable_slot: int = 1,
    ) -> list[CuratedRecommendation]:
        """Boost a recommendation based on preferred topic(s) into `boostable_slot`.

        :param recs: List of recommendations from which an item is boosted based on preferred topic(s).
        :param preferred_topics: user's preferred topic(s)
        :param boostable_slot: 0-based slot to boost an item into. Defaults to slot 1,
        which is the second recommendation.
        :return: CuratedRecommendations ranked based on a preferred topic, while otherwise preserving the order.
        """
        # get the first item found to boost based on the below condition starting after the boostable_slot in the list.
        # condition for boostable item: check if an item has a topic in the preferred_topics list.
        boostable_rec = next(
            (r for r in recs[boostable_slot + 1 :] if r.topic in preferred_topics),
            None,
        )

        # if item to boost is found
        if boostable_rec:
            recs = copy(recs)  # Create a shallow copy of recs
            recs.remove(boostable_rec)  # remove the item to boost from list of recs
            recs.insert(
                boostable_slot, boostable_rec
            )  # insert it into the boostable_slot (2nd rec)

        return recs

    async def fetch(
        self, curated_recommendations_request: CuratedRecommendationsRequest
    ) -> CuratedRecommendationsResponse:  # noqa
        """Provide curated recommendations."""
        # get the recommendation surface ID based on passed locale & region
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

        # 3. Apply Thompson sampling to rank recommendations by engagement
        recommendations = thompson_sampling(recommendations, self.engagement_backend)

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
