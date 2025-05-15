"""Utility functions for curated recommendations"""

import re
import time

from urllib.parse import quote
from pydantic import HttpUrl
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsRequest,
    Locale,
    CuratedRecommendation,
    CuratedRecommendationLegacy,
    CuratedRecommendationGlobalLegacy,
)


def get_recommendation_surface_id(locale: Locale, region: str | None = None) -> SurfaceId:
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
    language = extract_language_from_locale(locale)
    derived_region = derive_region(locale, region)

    if language == "de":
        return SurfaceId.NEW_TAB_DE_DE
    elif language == "es":
        return SurfaceId.NEW_TAB_ES_ES
    elif language == "fr":
        return SurfaceId.NEW_TAB_FR_FR
    elif language == "it":
        return SurfaceId.NEW_TAB_IT_IT
    else:
        # Default to English language for all other values of language (including 'en' or None)
        if derived_region is None or derived_region in ["US", "CA"]:
            return SurfaceId.NEW_TAB_EN_US
        elif derived_region in ["GB", "IE"]:
            return SurfaceId.NEW_TAB_EN_GB
        elif derived_region in ["IN"]:
            return SurfaceId.NEW_TAB_EN_INTL
        else:
            # Default to the en-US New Tab if no 2-letter region can be derived from locale or region.
            return SurfaceId.NEW_TAB_EN_US


def extract_language_from_locale(locale: Locale) -> str | None:
    """Return a 2-letter language code from a locale string like 'en-US' or 'en'."""
    match = re.search(r"[a-zA-Z]{2}", locale)
    if match:
        return match.group().lower()
    else:
        return None


def derive_region(locale: Locale, region: str | None = None) -> str | None:
    """Derive the region from the `region` argument if provided, otherwise try to extract from the locale.

    Args:
         locale: The language-variant preferred by the user (e.g. 'en-US' means English-as-spoken in the US)
         region: Optionally, the geographic region of the user, e.g. 'US'.

    Return a 2-letter region like 'US'.
    """
    if region:
        m1 = re.search(r"[a-zA-Z]{2}", region)
        if m1:
            return m1.group().upper()
    m2 = re.search(r"[_\-]([a-zA-Z]{2})", locale)
    if m2:
        return m2.group(1).upper()
    else:
        return None


def is_enrolled_in_experiment(
    request: CuratedRecommendationsRequest, name: str, branch: str
) -> bool:
    """Return True if the request's experimentName matches name or "optin-" + name, and the
    experimentBranch matches the given branch. The optin- prefix signifies a forced enrollment.
    """
    return (
        request.experimentName == name or request.experimentName == f"optin-{name}"
    ) and request.experimentBranch == branch


def get_millisecond_epoch_time() -> int:
    """Return the time in milliseconds since the epoch as an integer."""
    return int(time.time() * 1000)


def transform_image_url_to_pocket_cdn(original_url: HttpUrl) -> HttpUrl:
    """Transform an original image URL to a Pocket CDN URL for the given image with a fixed width of 450px.

    The original URL is encoded and embedded as a query parameter.
    """
    encoded_url = quote(str(original_url), safe="")
    return HttpUrl(f"https://img-getpocket.cdn.mozilla.net/direct?url={encoded_url}&resize=w450")


def map_curated_recommendations_to_legacy_recommendations(
    base_recommendations: list[CuratedRecommendation],
) -> list[CuratedRecommendationLegacy]:
    """Map CuratedRecommendation object to CuratedRecommendationDesktopLegacy"""
    return [
        CuratedRecommendationLegacy(
            typename="Recommendation",
            recommendationId=item.corpusItemId,
            tileId=item.tileId,
            url=item.url,
            title=item.title,
            excerpt=item.excerpt,
            publisher=item.publisher,
            imageUrl=item.imageUrl,
        )
        for item in base_recommendations
    ]


def map_curated_recommendations_to_legacy_global_recommendations(
    base_recommendations: list[CuratedRecommendation],
) -> list[CuratedRecommendationGlobalLegacy]:
    """Map CuratedRecommendation object to CuratedRecommendationGlobalLegacy"""
    return [
        CuratedRecommendationGlobalLegacy(
            id=item.tileId,
            title=item.title,
            url=item.url,
            excerpt=item.excerpt,
            domain=item.publisher,
            image_src=transform_image_url_to_pocket_cdn(item.imageUrl),
            raw_image_src=item.imageUrl,
        )
        for item in base_recommendations
    ]
