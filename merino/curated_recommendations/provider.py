"""Provider for curated recommendations on New Tab."""

import time
import re
from typing import cast

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    ScheduledSurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    Locale,
    CuratedRecommendation,
    CuratedRecommendationsRequest,
    CuratedRecommendationsResponse,
    ExperimentName,
    CuratedRecommendationsFeed,
    CuratedRecommendationsBucket,
)
from merino.curated_recommendations.rankers import (
    boost_preferred_topic,
    spread_publishers,
    thompson_sampling,
)


class CuratedRecommendationsProvider:
    """Provider for recommendations that have been reviewed by human curators."""

    corpus_backend: CorpusBackend

    def __init__(
        self,
        corpus_backend: CorpusBackend,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
    ) -> None:
        self.corpus_backend = corpus_backend
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend

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
    def is_enrolled_in_experiment(
        request: CuratedRecommendationsRequest, name: str, branch: str
    ) -> bool:
        """Return True if the request's experimentName matches name or "optin-" + name, and the
        experimentBranch matches the given branch. The optin- prefix signifies a forced enrollment.
        """
        return (
            request.experimentName == name or request.experimentName == f"optin-{name}"
        ) and request.experimentBranch == branch

    @staticmethod
    def is_enrolled_in_regional_engagement(request: CuratedRecommendationsRequest) -> bool:
        """Return True if Thompson sampling should use regional engagement (treatment)."""
        return CuratedRecommendationsProvider.is_enrolled_in_experiment(
            request, ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION.value, "treatment"
        )

    def rank_recommendations(
        self,
        recommendations: list[CuratedRecommendation],
        surface_id: str,
        request: CuratedRecommendationsRequest,
    ):
        """Apply additional processing to the list of recommendations
        received from Curated Corpus API

        @param recommendations: A list of CuratedRecommendation objects as they are received
        from Curated Corpus API
        @param surface_id: a string identifier for the New Tab surface these recommendations
        are intended for
        @param request: The full API request with all the data
        @return: A re-ranked list of curated recommendations
        """
        # 3. Apply Thompson sampling to rank recommendations by engagement
        recommendations = thompson_sampling(
            recommendations,
            engagement_backend=self.engagement_backend,
            prior_backend=self.prior_backend,
            region=self.derive_region(request.locale, request.region),
            enable_region_engagement=self.is_enrolled_in_regional_engagement(request),
        )

        # 2. Perform publisher spread on the recommendation set
        recommendations = spread_publishers(recommendations, spread_distance=3)

        # 1. Finally, perform preferred topics boosting if preferred topics are passed in the request
        if request.topics:
            validated_topics: list[Topic] = cast(list[Topic], request.topics)
            recommendations = boost_preferred_topic(recommendations, validated_topics)

        # 0. Blast-off!
        for rank, rec in enumerate(recommendations):
            # Update received_rank now that recommendations have been ranked.
            rec.receivedRank = rank

            # Topic labels are enabled only for en-US in Fx130. We are unsure about the quality of
            # localized topic strings in Firefox. As a workaround, we decided to only send topics
            # for New Tab en-US. This workaround should be removed once Fx131 is released on Oct 1.
            if surface_id not in (
                ScheduledSurfaceId.NEW_TAB_EN_US,
                ScheduledSurfaceId.NEW_TAB_EN_GB,
            ):
                rec.topic = None

        return recommendations

    def rank_need_to_know_recommendations(
        self,
        recommendations: list[CuratedRecommendation],
        surface_id: ScheduledSurfaceId,
        request: CuratedRecommendationsRequest,
    ):
        """Apply additional processing to the list of recommendations
        received from Curated Corpus API, splitting the list in two:
        the "general" feed and the "need to know" feed

        @param recommendations: A list of CuratedRecommendation objects as they are received
        from Curated Corpus API
        @param surface_id: a string identifier for the New Tab surface these recommendations
        are intended for
        @param request: The full API request with all the data
        @return: A tuple with two re-ranked lists of curated recommendations and a localised
        title for the "Need to Know" heading
        """
        # Filter out all time-sensitive recommendations into the need_to_know feed
        need_to_know_feed = [r for r in recommendations if r.isTimeSensitive]

        # Update received_rank for need_to_know recommendations
        for rank, rec in enumerate(need_to_know_feed):
            rec.receivedRank = rank

        # Place the remaining recommendations in the general feed
        general_feed = [r for r in recommendations if r not in need_to_know_feed]

        # Apply all the additional re-ranking and processing steps
        # to the main recommendations feed
        general_feed = self.rank_recommendations(general_feed, surface_id, request)

        # Provide a localized title string for the "Need to Know" feed.
        localized_titles = {
            ScheduledSurfaceId.NEW_TAB_EN_US: "Need to Know",
            ScheduledSurfaceId.NEW_TAB_EN_GB: "Need to Know in British English",
            ScheduledSurfaceId.NEW_TAB_DE_DE: "Need to Know auf Deutsch",
        }
        title = localized_titles[surface_id]

        return general_feed, need_to_know_feed, title

    async def fetch(
        self, curated_recommendations_request: CuratedRecommendationsRequest
    ) -> CuratedRecommendationsResponse:
        """Provide curated recommendations."""
        # Get the recommendation surface ID based on passed locale & region
        surface_id = CuratedRecommendationsProvider.get_recommendation_surface_id(
            curated_recommendations_request.locale,
            curated_recommendations_request.region,
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

        # For users in the "Need to Know" experiment, separate recommendations into
        # two different feeds: the "general" feed and the "need to know" feed.
        if (
            curated_recommendations_request.feeds
            and "need_to_know" in curated_recommendations_request.feeds
            and surface_id
            in (
                ScheduledSurfaceId.NEW_TAB_EN_US,
                ScheduledSurfaceId.NEW_TAB_EN_GB,
                ScheduledSurfaceId.NEW_TAB_DE_DE,
            )
        ):
            general_feed, need_to_know_feed, title = self.rank_need_to_know_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

            return CuratedRecommendationsResponse(
                recommendedAt=self.time_ms(),
                data=general_feed,
                feeds=CuratedRecommendationsFeed(
                    need_to_know=CuratedRecommendationsBucket(
                        recommendations=need_to_know_feed, title=title
                    ),
                ),
            )
        # For everyone else, return the "classic" New Tab list of recommendations
        else:
            # Apply all the additional re-ranking and processing steps
            # to the main recommendations feed
            recommendations = self.rank_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

            return CuratedRecommendationsResponse(
                recommendedAt=self.time_ms(),
                data=recommendations,
            )

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)
