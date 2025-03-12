"""Provider for curated recommendations on New Tab."""

import logging
import time
import re
from typing import cast

from merino.curated_recommendations.corpus_backends.protocol import (
    DatedCorpusBackend,
    ScheduledSurfaceId,
    Topic,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
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
    CuratedRecommendationsFeed,
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

    corpus_backend: DatedCorpusBackend

    def __init__(
        self,
        corpus_backend: DatedCorpusBackend,
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
            max_tile_count = section.layout.max_tile_count
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
        self.set_double_row_layout(feeds)

        return feeds

    @staticmethod
    def set_double_row_layout(feeds: CuratedRecommendationsFeed):
        """Apply the double row layout with 3 ads on the second section in the feed,
        only if the second section exists and has enough recommendations.
        """
        second_section = next(
            (s for s, _ in feeds.get_sections() if s.receivedFeedRank == 1), None
        )
        # Only change the layout if there is a second section, and if it contains enough recommendations.
        if second_section and len(second_section.recommendations) >= layout_3_ads.max_tile_count:
            second_section.layout = layout_3_ads

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

        # The sections experiment organizes recommendations in many feeds
        sections_feeds = None

        if self.is_sections_experiment(curated_recommendations_request, surface_id):
            sections_feeds = await self.get_sections(
                recommendations, curated_recommendations_request, surface_id
            )
            general_feed = []  # Everything is organized into sections. There's no 'general' feed.
        else:
            # Default ranking for general feed
            general_feed = self.rank_recommendations(
                recommendations, surface_id, curated_recommendations_request
            )

        # Construct the base response
        response = CuratedRecommendationsResponse(
            recommendedAt=self.time_ms(), surfaceId=surface_id, data=general_feed
        )

        # If we have feeds to return, add those to the response
        if sections_feeds:
            response.feeds = sections_feeds

        if curated_recommendations_request.enableInterestPicker and response.feeds:
            interest_picker = create_interest_picker(response.feeds.get_sections())
            response.interestPicker = interest_picker

        return response

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)
