"""Provider for curated recommendations on New Tab."""

import orjson
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
    FakespotFeed,
    FakespotProduct,
    FAKESPOT_HEADER_COPY,
    FAKESPOT_FOOTER_COPY,
    FAKESPOT_CTA_COPY,
    FAKESPOT_CTA_URL,
    FakespotCTA,
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
        # Large and small countries need a different enrollment %, thus require separate experiments
        return CuratedRecommendationsProvider.is_enrolled_in_experiment(
            request, ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION.value, "treatment"
        ) or CuratedRecommendationsProvider.is_enrolled_in_experiment(
            request,
            ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION_SMALL.value,
            "treatment",
        )

    @staticmethod
    def is_need_to_know_experiment(request, surface_id) -> bool:
        """Check if the 'need_to_know' experiment is enabled."""
        return (
            request.feeds
            and "need_to_know" in request.feeds
            and surface_id
            in (
                ScheduledSurfaceId.NEW_TAB_EN_US,
                ScheduledSurfaceId.NEW_TAB_EN_GB,
                ScheduledSurfaceId.NEW_TAB_DE_DE,
            )
        )

    @staticmethod
    def is_fakespot_experiment(request, surface_id) -> bool:
        """Check if the 'Fakespot' experiment is enabled."""
        return (
            request.feeds
            and "fakespot" in request.feeds
            and surface_id == ScheduledSurfaceId.NEW_TAB_EN_US
        )

    @staticmethod
    def get_fakespot_feed() -> FakespotFeed:
        """Construct & return the Fakespot feed. Currently, reading data from a mock JSON file."""
        # TODO: https://mozilla-hub.atlassian.net/browse/MC-1566
        # retrieve fakespot products from JSON blob in GCS
        # add error/exception handling when reading from GCS
        with open("merino/curated_recommendations/fakespot_products.json", "rb") as f:
            fakespot_products_json_data = orjson.loads(f.read())

            fakespot_products = []
            for product in fakespot_products_json_data:
                fakespot_products.append(
                    FakespotProduct(
                        id=product["id"],
                        title=product["title"],
                        category=product["category"],
                        imageUrl=product["imageUrl"],
                        url=product["url"],
                    )
                )
        return FakespotFeed(
            products=fakespot_products,
            headerCopy=FAKESPOT_HEADER_COPY,
            footerCopy=FAKESPOT_FOOTER_COPY,
            cta=FakespotCTA(ctaCopy=FAKESPOT_CTA_COPY, url=FAKESPOT_CTA_URL),
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

        return recommendations[: request.count]

    async def rank_need_to_know_recommendations(
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

        # If fewer than five stories have been curated for this feed, use yesterday's data
        if len(need_to_know_feed) < 5:
            yesterdays_recs = await self.fetch_backup_recommendations(surface_id)
            need_to_know_feed = [r for r in yesterdays_recs if r.isTimeSensitive]

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
            ScheduledSurfaceId.NEW_TAB_EN_US: "In the news",
            ScheduledSurfaceId.NEW_TAB_EN_GB: "In the news",
            ScheduledSurfaceId.NEW_TAB_DE_DE: "In den News",
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

        # Recommended articles for the "need to know/TBR" experiment
        need_to_know_feed = None
        # Fakespot products for the Fakespot experiment
        fakespot_feed = None

        # For users in the "Need to Know" experiment, separate recommendations into
        # two different feeds: the "general" feed and the "need to know" feed.
        if self.is_need_to_know_experiment(curated_recommendations_request, surface_id):
            # this applies ranking to the general_feed!
            general_feed, need_to_know_recs, title = await self.rank_need_to_know_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

            need_to_know_feed = CuratedRecommendationsBucket(
                recommendations=need_to_know_recs, title=title
            )
        else:
            # Default ranking for general feed
            general_feed = self.rank_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

        # Check for Fakespot feed experiment, currently, only for en-US
        if self.is_fakespot_experiment(curated_recommendations_request, surface_id):
            fakespot_feed = self.get_fakespot_feed()

        # Construct the base response
        response = CuratedRecommendationsResponse(recommendedAt=self.time_ms(), data=general_feed)

        # If we have feeds to return, add those to the response
        if need_to_know_feed is not None or fakespot_feed is not None:
            response.feeds = CuratedRecommendationsFeed(
                need_to_know=need_to_know_feed, fakespot=fakespot_feed
            )

        return response

    async def fetch_backup_recommendations(
        self, surface_id: ScheduledSurfaceId
    ) -> list[CuratedRecommendation]:
        """Return recommended stories for yesterday's date
        for a given New Tab surface

        @param: surface_id: a ScheduledSurfaceId
        @return: A re-ranked list of curated recommendations
        """
        corpus_items = await self.corpus_backend.fetch(surface_id, -1)

        # Convert the CorpusItem list to a CuratedRecommendation list.
        recommendations = [
            CuratedRecommendation(
                **item.model_dump(),
                receivedRank=rank,
            )
            for rank, item in enumerate(corpus_items)
        ]

        return recommendations

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)
