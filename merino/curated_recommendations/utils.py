"""Utility functions for curated recommendations"""

import re
import time

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.protocol import CuratedRecommendationsRequest, Locale


def get_recommendation_surface_id(
    locale: Locale,
    region: str | None = None,
    request: "CuratedRecommendationsRequest | None" = None,
) -> SurfaceId:
    """Locale/region mapping is documented here:
    https://docs.google.com/document/d/1omclr-eETJ7zAWTMI7mvvsc3_-ns2Iiho4jPEfrmZfo/edit

    Args:
        locale: The language variant preferred by the user (e.g. 'en-US', or 'en')
        region: Optionally, the geographic region of the user, e.g. 'US'.
        request: Optionally, the full request object for experiment checks.

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
        if derived_region == "CA":
            # Canada routing: Map to NEW_TAB_EN_CA only if:
            # 1. Request includes 'sections' in feeds
            # 2. User is in 'sections' branch of 'sections-in-canada' experiment
            # Otherwise, default to NEW_TAB_EN_US
            if (
                request is not None
                and request.feeds is not None
                and "sections" in request.feeds
                and is_enrolled_in_experiment(request, "sections-in-canada", "sections")
            ):
                return SurfaceId.NEW_TAB_EN_CA
            else:
                return SurfaceId.NEW_TAB_EN_US
        elif derived_region is None or derived_region == "US":
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
