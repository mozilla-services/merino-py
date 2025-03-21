"""Provider for curated recommendations on New Tab."""

import logging
import time
import re
from typing import cast

from merino.curated_recommendations import ExtendedExpirationCorpusBackend
from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    ScheduledSurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.fakespot_backend.protocol import (
    FakespotBackend,
)
from merino.curated_recommendations.interest_picker import create_interest_picker
from merino.curated_recommendations.layouts import (
    layout_4_medium,
    layout_4_large,
    layout_6_tiles,
    layout_3_ads,
)
from merino.curated_recommendations.localization import get_translation, LOCALIZED_SECTION_TITLES
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
    Section,
)
from merino.curated_recommendations.rankers import (
    boost_preferred_topic,
    spread_publishers,
    thompson_sampling,
    boost_followed_sections,
)

logger = logging.getLogger(__name__)


class CuratedRecommendationsProvider:
    """Provider for recommendations that have been reviewed by human curators."""

    corpus_backend: CorpusBackend

    def __init__(
        self,
        corpus_backend: CorpusBackend,
        extended_expiration_corpus_backend: ExtendedExpirationCorpusBackend,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
        fakespot_backend: FakespotBackend,
    ) -> None:
        self.corpus_backend = corpus_backend
        self.extended_expiration_corpus_backend = extended_expiration_corpus_backend
        self.engagement_backend = engagement_backend
        self.prior_backend = prior_backend
        self.fakespot_backend = fakespot_backend

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
    def is_in_extended_expiration_experiment(request: CuratedRecommendationsRequest) -> bool:
        """Return True if Thompson sampling should use regional engagement (treatment)."""
        return CuratedRecommendationsProvider.is_enrolled_in_experiment(
            request, ExperimentName.EXTENDED_EXPIRATION_EXPERIMENT.value, "treatment"
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
    def is_sections_experiment(
        request: CuratedRecommendationsRequest,
        surface_id: ScheduledSurfaceId,
    ) -> bool:
        """Check if the 'sections' experiment is enabled."""
        return (
            request.feeds is not None
            and "sections" in request.feeds  # Clients must request "feeds": ["sections"]
            and surface_id in LOCALIZED_SECTION_TITLES  # The locale must be supported
        )

    @staticmethod
    def is_double_row_layout_experiment(request: CuratedRecommendationsRequest) -> bool:
        """Check if the double row layout experiment is enabled."""
        return CuratedRecommendationsProvider.is_enrolled_in_experiment(
            request, ExperimentName.DOUBLE_ROW_LAYOUT_EXPERIMENT.value, "treatment"
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
    def get_fakespot_feed(
        fakespot_backend: FakespotBackend, surface_id: ScheduledSurfaceId
    ) -> FakespotFeed | None:
        """Return the fakespot feed constructed in Fakespot Backend."""
        return fakespot_backend.get(surface_id)

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
    ) -> tuple[list[CuratedRecommendation], list[CuratedRecommendation], str]:
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
        general_feed, need_to_know_feed = await self.get_time_sensitive_recommendations(
            recommendations, surface_id
        )

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

    async def get_time_sensitive_recommendations(
        self, recommendations: list[CuratedRecommendation], surface_id: ScheduledSurfaceId
    ) -> tuple[list[CuratedRecommendation], list[CuratedRecommendation]]:
        """Split the recommendations in two: the "general" feed and "time-sensitive" feed

        @param recommendations: A list of CuratedRecommendation objects as they are received
        from Curated Corpus API
        @param surface_id: a string identifier for the New Tab surface these recommendations
        are intended for
        @return: A tuple with two re-ranked lists: "general" and "time-sensitive" respectively.
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
        general_feed = [r for r in recommendations if not r.isTimeSensitive]
        return general_feed, need_to_know_feed

    @staticmethod
    def exclude_recommendations_from_blocked_sections(
        recommendations, requested_sections
    ) -> list[CuratedRecommendation]:
        """Return recommendations which topic doesn't match any blocked section"""
        blocked_section_ids = {rs.sectionId for rs in requested_sections if rs.isBlocked}
        return [
            r for r in recommendations if not r.topic or r.topic.value not in blocked_section_ids
        ]

    async def get_sections(
        self,
        recommendations: list[CuratedRecommendation],
        request: CuratedRecommendationsRequest,
        surface_id: ScheduledSurfaceId,
    ) -> CuratedRecommendationsFeed:
        """Return a CuratedRecommendationsFeed with recommendations mapped to their topic."""
        max_recs_per_section = 30
        # Section must have some extra items in case one is dismissed, beyond what can be displayed.
        min_fallback_recs_per_section = 1
        top_stories_count = 6

        # Recommendations whose topic matches a blocked section should not be shown.
        if request.sections:
            recommendations = self.exclude_recommendations_from_blocked_sections(
                recommendations, request.sections
            )

        # Apply Thompson sampling to rank all recommendations by engagement
        recommendations = thompson_sampling(
            recommendations,
            engagement_backend=self.engagement_backend,
            prior_backend=self.prior_backend,
            region=self.derive_region(request.locale, request.region),
        )

        top_stories = recommendations[:top_stories_count]
        remaining_recs = recommendations[top_stories_count:]

        # Renumber receivedRank for top_stories recommendations
        for rank, recommendation in enumerate(top_stories):
            recommendation.receivedRank = rank

        # Create "Today's top stories" section with the first 6 recommendations
        feeds = CuratedRecommendationsFeed(
            top_stories_section=Section(
                receivedFeedRank=0,
                recommendations=top_stories,
                title=get_translation(surface_id, "top-stories", "Popular Today"),
                layout=layout_4_large,
            ),
        )

        # Group the remaining recommendations by topic, preserving Thompson sampling order
        sections_by_topic: dict[Topic, Section] = {}
        # Sections will cycle through the following layouts.
        topic_layout_order = [
            layout_6_tiles,
            layout_4_large,
            layout_4_medium,
        ]

        for rec in remaining_recs:
            if rec.topic:
                if rec.topic in sections_by_topic:
                    section = sections_by_topic[rec.topic]
                else:
                    formatted_topic_en_us = rec.topic.replace("_", " ").capitalize()
                    section = sections_by_topic[rec.topic] = Section(
                        receivedFeedRank=len(sections_by_topic) + 1,  # +1 for top_stories_section
                        recommendations=[],
                        # return the hardcoded localized topic section title
                        # fallback on en-US topic title
                        title=get_translation(surface_id, rec.topic, formatted_topic_en_us),
                        layout=topic_layout_order[
                            len(sections_by_topic) % len(topic_layout_order)
                        ],
                    )

                if len(section.recommendations) < max_recs_per_section:
                    rec.receivedRank = len(section.recommendations)
                    section.recommendations.append(rec)

        # Only keep sections with enough recommendations.
        valid_sections_by_topic = {}
        for topic, section in sections_by_topic.items():
            # Find the number of tiles in the biggest responsive layout.
            max_tile_count = max(len(rl.tiles) for rl in section.layout.responsiveLayouts)
            # Keep the section if it has enough recs to fill its biggest layout, plus fallback recs.
            if len(section.recommendations) >= max_tile_count + min_fallback_recs_per_section:
                valid_sections_by_topic[topic] = section

        # The above loop may have dropped some sections. Renumber receivedFeedRank to 0, 1, 2,...
        sorted_sections = sorted(
            valid_sections_by_topic.items(), key=lambda item: item[1].receivedFeedRank
        )
        for index, (topic, section) in enumerate(sorted_sections):
            section.receivedFeedRank = index + 1  # +1 for top_stories_section
            feeds.set_topic_section(topic, section)

        # Boost followed sections, if any are provided with the request.
        if request.sections and feeds:
            feeds = boost_followed_sections(request.sections, feeds)

        # Set the layout of the second section to have 3 ads, to match the number of ads in control.
        if self.is_double_row_layout_experiment(request):
            second_section = next(
                (s for s, _ in feeds.get_sections() if s.receivedFeedRank == 1), None
            )
            if second_section:
                second_section.layout = layout_3_ads

        return feeds

    async def fetch(
        self, curated_recommendations_request: CuratedRecommendationsRequest
    ) -> CuratedRecommendationsResponse:
        """Provide curated recommendations."""
        # Get the recommendation surface ID based on passed locale & region
        surface_id = CuratedRecommendationsProvider.get_recommendation_surface_id(
            curated_recommendations_request.locale,
            curated_recommendations_request.region,
        )

        if self.is_in_extended_expiration_experiment(curated_recommendations_request):
            corpus_items = await self.extended_expiration_corpus_backend.fetch(surface_id)
        else:
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
        # The sections experiment organizes recommendations in many feeds
        sections_feeds = None

        if self.is_need_to_know_experiment(curated_recommendations_request, surface_id):
            # this applies ranking to the general_feed!
            general_feed, need_to_know_recs, title = await self.rank_need_to_know_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

            need_to_know_feed = CuratedRecommendationsBucket(
                recommendations=need_to_know_recs, title=title
            )
        elif self.is_sections_experiment(curated_recommendations_request, surface_id):
            sections_feeds = await self.get_sections(
                recommendations, curated_recommendations_request, surface_id
            )
            general_feed = []  # Everything is organized into sections. There's no 'general' feed.
        else:
            # Default ranking for general feed
            general_feed = self.rank_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

        # Check for Fakespot feed experiment, currently, only for en-US
        if self.is_fakespot_experiment(curated_recommendations_request, surface_id):
            fakespot_feed = self.get_fakespot_feed(self.fakespot_backend, surface_id)

        # Construct the base response
        response = CuratedRecommendationsResponse(
            recommendedAt=self.time_ms(), surfaceId=surface_id, data=general_feed
        )

        # If we have feeds to return, add those to the response
        if need_to_know_feed or fakespot_feed:
            response.feeds = CuratedRecommendationsFeed(
                need_to_know=need_to_know_feed, fakespot=fakespot_feed
            )
        elif sections_feeds:
            response.feeds = sections_feeds

        if curated_recommendations_request.enableInterestPicker and response.feeds:
            interest_picker = create_interest_picker(response.feeds.get_sections())
            response.interestPicker = interest_picker

        return response

    async def fetch_backup_recommendations(
        self, surface_id: ScheduledSurfaceId
    ) -> list[CuratedRecommendation]:
        """Return recommended stories for yesterday's date for a given New Tab surface.

        Note that there's no fallback for if no appropriate stories are available in
        yesterday's data. We rely on the curators' commitment to always have this data
        for the previous day.

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
