"""Unit test for CuratedRecommendationsProvider."""

import pytest

from merino.curated_recommendations.corpus_backends.protocol import RecommendationSurfaceId
from merino.curated_recommendations.provider import CuratedRecommendationsProvider, Locale


@pytest.mark.parametrize(
    "locale, language",
    [
        ("fr", "fr"),
        ("fr-FR", "fr"),
        ("es", "es"),
        ("es-ES", "es"),
        ("it", "it"),
        ("it-IT", "it"),
        ("en", "en"),
        ("en-CA", "en"),
        ("en-GB", "en"),
        ("en-US", "en"),
        ("de", "de"),
        ("de-DE", "de"),
        ("de-AT", "de"),
        ("de-CH", "de"),
    ],
)
def test_extract_language_from_locale(locale, language):
    """Testing the extract_language_from_locale() method
    & ensure appropriate language is returned.
    """
    assert CuratedRecommendationsProvider.extract_language_from_locale(Locale(locale)) == language


def test_extract_language_from_locale_return_none():
    """Testing the extract_language_from_locale() method
    & ensure if no match is found, return None
    """
    assert CuratedRecommendationsProvider.extract_language_from_locale("1234") is None


@pytest.mark.parametrize(
    "locale, region",
    [
        ("fr-FR", "FR"),
        ("es-ES", "ES"),
        ("it-IT", "IT"),
        ("en-CA", "CA"),
        ("en-GB", "GB"),
        ("en-US", "US"),
        ("de-DE", "DE"),
        ("de-AT", "AT"),
        ("de-CH", "CH"),
    ],
)
def test_derive_region_from_locale(locale, region):
    """Testing the derive_region() method & ensuring region is derived
    if only locale is provided
    """
    assert CuratedRecommendationsProvider.derive_region(Locale(locale)) == region


@pytest.mark.parametrize(
    "locale, region, derived_region",
    [
        ("de", "US", "US"),
        ("en", "FR", "FR"),
        ("es", "DE", "DE"),
        ("fr", "ES", "ES"),
        ("it", "CA", "CA"),
    ],
)
def test_derive_region_from_region(locale, region, derived_region):
    """Testing the derive_region() method & ensure region is derived
    from region if region is provided
    """
    assert CuratedRecommendationsProvider.derive_region(Locale(locale), region) == derived_region


def test_derive_region_return_none():
    """Testing the derive_region() method &
    ensure if no match is found, return None
    """
    # if region is passed
    assert CuratedRecommendationsProvider.derive_region("123", "123") is None
    # if only locale is passed
    assert CuratedRecommendationsProvider.derive_region("123") is None
    # if only locale is passed
    assert CuratedRecommendationsProvider.derive_region("en") is None


@pytest.mark.parametrize(
    "locale,region,recommendation_surface_id",
    [
        # Test cases below are from the Newtab locales/region documentation maintained by the Firefox integration team:
        # https://docs.google.com/document/d/1omclr-eETJ7zAWTMI7mvvsc3_-ns2Iiho4jPEfrmZfo/edit
        # Ref: https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/tests/unit/data_providers/test_new_tab_dispatch.py#L7 # noqa
        ("en-CA", "US", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-GB", "US", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-US", "US", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-CA", "CA", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-GB", "CA", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-US", "CA", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("de", "DE", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("de-AT", "DE", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("de-CH", "DE", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("en-CA", "GB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-GB", "GB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-US", "GB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-CA", "IE", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-GB", "IE", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-US", "IE", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("fr", "FR", RecommendationSurfaceId.NEW_TAB_FR_FR),
        ("it", "IT", RecommendationSurfaceId.NEW_TAB_IT_IT),
        ("es", "ES", RecommendationSurfaceId.NEW_TAB_ES_ES),
        ("en-CA", "IN", RecommendationSurfaceId.NEW_TAB_EN_INTL),
        ("en-GB", "IN", RecommendationSurfaceId.NEW_TAB_EN_INTL),
        ("en-US", "IN", RecommendationSurfaceId.NEW_TAB_EN_INTL),
        ("de", "CH", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("de", "AT", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("de", "BE", RecommendationSurfaceId.NEW_TAB_DE_DE),
        # Locale can be a main language only.
        ("en", "CA", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en", "US", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en", "GB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en", "IE", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en", "IN", RecommendationSurfaceId.NEW_TAB_EN_INTL),
        # The locale language primarily determines the market, even if it's not the most common language in the region.
        ("de", "US", RecommendationSurfaceId.NEW_TAB_DE_DE),
        ("en", "FR", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("es", "DE", RecommendationSurfaceId.NEW_TAB_ES_ES),
        ("fr", "ES", RecommendationSurfaceId.NEW_TAB_FR_FR),
        ("it", "CA", RecommendationSurfaceId.NEW_TAB_IT_IT),
        # Extract region from locale, if it is not explicitly provided.
        ("en-US", None, RecommendationSurfaceId.NEW_TAB_EN_US),
        ("en-GB", None, RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-IE", None, RecommendationSurfaceId.NEW_TAB_EN_GB),
        # locale can vary in case.
        ("eN-US", None, RecommendationSurfaceId.NEW_TAB_EN_US),
        ("En-GB", None, RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("EN-ie", None, RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en-cA", None, RecommendationSurfaceId.NEW_TAB_EN_US),
        # region can vary in case.
        ("en", "gB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en", "Ie", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("en", "in", RecommendationSurfaceId.NEW_TAB_EN_INTL),
        # Default to international NewTab when region is unknown.
        ("en", "XX", RecommendationSurfaceId.NEW_TAB_EN_US),
        # Default to English when language is unknown.
        ("xx", "US", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("xx", "CA", RecommendationSurfaceId.NEW_TAB_EN_US),
        ("xx", "GB", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("xx", "IE", RecommendationSurfaceId.NEW_TAB_EN_GB),
        ("xx", "YY", RecommendationSurfaceId.NEW_TAB_EN_US),
    ],
)
def test_get_recommendation_surface_id(
    locale: Locale, region: str, recommendation_surface_id: RecommendationSurfaceId
):
    """Testing the get_recommendation_surface_id() method &
    ensure correct surface id is returned based on passed locale & region
    """
    assert (
        CuratedRecommendationsProvider.get_recommendation_surface_id(locale, region)
        == recommendation_surface_id
    )
