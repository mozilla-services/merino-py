import pytest

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.protocol import Locale
from merino.curated_recommendations.utils import (
    derive_region,
    extract_language_from_locale,
    get_recommendation_surface_id,
)


class TestCuratedRecommendationsProviderExtractLanguageFromLocale:
    """Unit tests for extract_language_from_locale."""

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
    def test_extract_language_from_locale(self, locale, language):
        """Testing the extract_language_from_locale() method
        & ensure appropriate language is returned.
        """
        assert (
            extract_language_from_locale(Locale(locale)) == language
        )

    def test_extract_language_from_locale_return_none(self):
        """Testing the extract_language_from_locale() method
        & ensure if no match is found, return None
        """
        assert extract_language_from_locale("1234") is None


class TestCuratedRecommendationsProviderDeriveRegion:
    """Unit tests for derive_region."""

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
    def test_derive_region_from_locale(self, locale, region):
        """Testing the derive_region() method & ensuring region is derived
        if only locale is provided
        """
        assert derive_region(Locale(locale)) == region

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
    def test_derive_region_from_region(self, locale, region, derived_region):
        """Testing the derive_region() method & ensure region is derived
        from region if region is provided
        """
        assert (
            derive_region(Locale(locale), region) == derived_region
        )

    def test_derive_region_return_none(self):
        """Testing the derive_region() method &
        ensure if no match is found, return None
        """
        # if region is passed
        assert derive_region("123", "123") is None
        # if only locale is passed
        assert derive_region("123") is None
        # if only locale is passed
        assert derive_region("en") is None


class TestCuratedRecommendationsProviderGetRecommendationSurfaceId:
    """Unit tests for get_recommendation_surface_id."""

    @pytest.mark.parametrize(
        "locale,region,recommendation_surface_id",
        [
            # Test cases below are from the Newtab locales/region documentation maintained by the Firefox integration
            # team: https://docs.google.com/document/d/1omclr-eETJ7zAWTMI7mvvsc3_-ns2Iiho4jPEfrmZfo/edit Ref:
            # https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/tests/unit
            # /data_providers/test_new_tab_dispatch.py#L7 # noqa
            ("en-CA", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-GB", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-US", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-CA", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en-GB", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en-US", "CA", SurfaceId.NEW_TAB_EN_US),
            ("de", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("de-AT", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("de-CH", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("en-CA", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-US", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-CA", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en-US", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("fr", "FR", SurfaceId.NEW_TAB_FR_FR),
            ("it", "IT", SurfaceId.NEW_TAB_IT_IT),
            ("es", "ES", SurfaceId.NEW_TAB_ES_ES),
            ("en-CA", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("en-GB", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("en-US", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("de", "CH", SurfaceId.NEW_TAB_DE_DE),
            ("de", "AT", SurfaceId.NEW_TAB_DE_DE),
            ("de", "BE", SurfaceId.NEW_TAB_DE_DE),
            # Locale can be a main language only.
            ("en", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en", "US", SurfaceId.NEW_TAB_EN_US),
            ("en", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en", "IN", SurfaceId.NEW_TAB_EN_INTL),
            # The locale language primarily determines the market, even if it's not the most common language in the region.
            ("de", "US", SurfaceId.NEW_TAB_DE_DE),
            ("en", "FR", SurfaceId.NEW_TAB_EN_US),
            ("es", "DE", SurfaceId.NEW_TAB_ES_ES),
            ("fr", "ES", SurfaceId.NEW_TAB_FR_FR),
            ("it", "CA", SurfaceId.NEW_TAB_IT_IT),
            # Extract region from locale, if it is not explicitly provided.
            ("en-US", None, SurfaceId.NEW_TAB_EN_US),
            ("en-GB", None, SurfaceId.NEW_TAB_EN_GB),
            ("en-IE", None, SurfaceId.NEW_TAB_EN_GB),
            # locale can vary in case.
            ("eN-US", None, SurfaceId.NEW_TAB_EN_US),
            ("En-GB", None, SurfaceId.NEW_TAB_EN_GB),
            ("EN-ie", None, SurfaceId.NEW_TAB_EN_GB),
            ("en-cA", None, SurfaceId.NEW_TAB_EN_US),
            # region can vary in case.
            ("en", "gB", SurfaceId.NEW_TAB_EN_GB),
            ("en", "Ie", SurfaceId.NEW_TAB_EN_GB),
            ("en", "in", SurfaceId.NEW_TAB_EN_INTL),
            # Default to international NewTab when region is unknown.
            ("en", "XX", SurfaceId.NEW_TAB_EN_US),
            # Default to English when language is unknown.
            ("xx", "US", SurfaceId.NEW_TAB_EN_US),
            ("xx", "CA", SurfaceId.NEW_TAB_EN_US),
            ("xx", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("xx", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("xx", "YY", SurfaceId.NEW_TAB_EN_US),
        ],
    )
    def test_get_recommendation_surface_id(
        self, locale: Locale, region: str, recommendation_surface_id: SurfaceId
    ):
        """Testing the get_recommendation_surface_id() method &
        ensure correct surface id is returned based on passed locale & region
        """
        assert (
            get_recommendation_surface_id(locale, region)
            == recommendation_surface_id
        )
