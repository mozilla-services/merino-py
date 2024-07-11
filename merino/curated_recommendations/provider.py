"""Provider for curated recommendations on New Tab."""

import time
import re

from copy import copy
from enum import Enum, unique

from pydantic import BaseModel

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    ScheduledSurfaceId,
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

        # Perform publisher spread on the recommendation set
        recommendations = CuratedRecommendationsProvider.spread_publishers(
            recommendations, spread_distance=3
        )

        return CuratedRecommendationsResponse(
            recommendedAt=self.time_ms(),
            data=recommendations,
        )

    @staticmethod
    def time_ms() -> int:
        """Return the time in milliseconds since the epoch as an integer."""
        return int(time.time() * 1000)
