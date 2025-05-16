"""Unit tests for LegacyCuratedRecommendationsProvider."""

from pydantic import HttpUrl
from merino.curated_recommendations.legacy.provider import (
    LegacyCuratedRecommendationsProvider,
    CuratedRecommendationLegacyFx115Fx129,
    CuratedRecommendationLegacyFx114,
)
from tests.unit.curated_recommendations.fixtures import generate_recommendations


def test_transform_image_url_to_pocket_cdn():
    """Test the static method to transform an image url to Pocket CDN encoded url"""
    original = HttpUrl("https://example.com/image.jpg")
    encoded = "https%3A%2F%2Fexample.com%2Fimage.jpg"
    expected = HttpUrl(f"https://img-getpocket.cdn.mozilla.net/direct?url={encoded}&resize=w450")

    result = LegacyCuratedRecommendationsProvider.transform_image_url_to_pocket_cdn(original)

    assert result == expected


def test_map_curated_recommendations_to_legacy_recommendations_fx115_129():
    """Test the static method to map base curated recommendations to Firefox v115-129 format"""
    base_recommendations = generate_recommendations(length=2)

    result = LegacyCuratedRecommendationsProvider.map_curated_recommendations_to_legacy_recommendations_fx_115_129(
        base_recommendations
    )

    # Assert structure and property mappings
    assert all(isinstance(item, CuratedRecommendationLegacyFx115Fx129) for item in result)
    assert len(result) == len(base_recommendations)

    for legacy, base in zip(result, base_recommendations):
        assert isinstance(legacy, CuratedRecommendationLegacyFx115Fx129)
        assert legacy.typename == "Recommendation"
        assert legacy.recommendationId == base.corpusItemId
        assert legacy.tileId == base.tileId
        assert legacy.url == base.url
        assert legacy.title == base.title
        assert legacy.excerpt == base.excerpt
        assert legacy.publisher == base.publisher
        assert legacy.imageUrl == base.imageUrl


def test_map_curated_recommendations_to_legacy_recommendations_fx114():
    """Test the static method to map base curated recommendations to Firefox v114 format"""
    base_recommendations = generate_recommendations(length=2)

    result = LegacyCuratedRecommendationsProvider.map_curated_recommendations_to_legacy_recommendations_fx_114(
        base_recommendations
    )

    # Assert structure and property mappings
    assert all(isinstance(item, CuratedRecommendationLegacyFx114) for item in result)
    assert len(result) == len(base_recommendations)

    for legacy, base in zip(result, base_recommendations):
        assert isinstance(legacy, CuratedRecommendationLegacyFx114)
        assert legacy.id == base.tileId
        assert legacy.title == base.title
        assert legacy.url == base.url
        assert legacy.excerpt == base.excerpt
        assert legacy.domain == base.publisher
        assert (
            legacy.image_src
            == LegacyCuratedRecommendationsProvider.transform_image_url_to_pocket_cdn(
                base.imageUrl
            )
        )
        assert legacy.raw_image_src == base.imageUrl
