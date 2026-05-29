"""Unit tests for CuratedRecommendationsProvider."""

import pytest
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, Topic
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.curated_recommendations.protocol import (
    MAX_TILE_ID,
    MIN_TILE_ID,
    CuratedRecommendation,
    CuratedRecommendationsRequest,
)


class TestCuratedRecommendationTileId:
    """Unit tests for CuratedRecommendation tileId generation."""

    # Common parameters for initializing CuratedRecommendation
    common_params = {
        "corpusItemId": "00000000-0000-0000-0000-000000000000",
        "url": HttpUrl("https://example.com"),
        "title": "Example Title",
        "excerpt": "Example Excerpt",
        "topic": Topic.CAREER,
        "publisher": "Example Publisher",
        "isTimeSensitive": False,
        "imageUrl": HttpUrl("https://example.com/image.jpg"),
        "receivedRank": 1,
    }

    @pytest.mark.parametrize(
        "scheduled_corpus_item_id, expected",
        [
            # Test random inputs. Boundary cases are not covered because sha256 is hard to reverse.
            ("550e8400-e29b-41d4-a716-446655440000", 367820988390657),
            ("6ba7b810-9dad-11d1-80b4-00c04fd430c8", 1754091520067902),
            ("123e4567-e89b-12d3-a456-426614174000", 1021785982574447),
            ("a3bb189e-8bf9-3888-9912-ace4e6543002", 4390412044299399),
            ("c1a5fc62-9a4e-43f3-b748-2106a12e8151", 8630494423250594),
        ],
    )
    def test_tile_id_generation(self, scheduled_corpus_item_id, expected):
        """Testing the tile_id generation in the CuratedRecommendation constructor."""
        # Create a CuratedRecommendation instance with the given scheduledCorpusItemId
        recommendation = CuratedRecommendation(
            scheduledCorpusItemId=scheduled_corpus_item_id,
            **self.common_params,
        )

        assert recommendation.tileId == expected

    @pytest.mark.parametrize("tile_id", [MIN_TILE_ID, MAX_TILE_ID])
    def test_tile_id_min_max(self, tile_id):
        """Test that the model can be initialized with MIN_TILE_ID and MAX_TILE_ID."""
        recommendation = CuratedRecommendation(
            scheduledCorpusItemId="550e8400-e29b-41d4-a716-446655440000",
            tileId=tile_id,
            **self.common_params,
        )
        assert recommendation.tileId == tile_id

    @pytest.mark.parametrize("invalid_tile_id", [0, 999999, -1, (1 << 53)])
    def test_invalid_tile_id(self, invalid_tile_id):
        """Test that the model cannot be initialized with invalid tile IDs."""
        with pytest.raises(ValueError):
            CuratedRecommendation(
                scheduledCorpusItemId="550e8400-e29b-41d4-a716-446655440000",
                tileId=invalid_tile_id,
                **self.common_params,
            )


class TestIsSectionsExperiment:
    """Unit tests for CuratedRecommendationsProvider.is_sections_experiment."""

    @pytest.mark.parametrize(
        "experiment_name, experiment_branch",
        [
            (None, None),
            ("sections-in-germany", "control"),
            ("sections-in-germany", "sections"),
            ("sections-in-germany-v2", "control"),
            ("sections-in-germany-v2", "content-only"),
            ("sections-in-germany-v2", "sections"),
            ("some-unrelated-experiment", "treatment"),
        ],
    )
    def test_de_with_sections_feed_returns_true_regardless_of_enrollment(
        self, experiment_name, experiment_branch
    ):
        """DE clients that request the sections feed get sections, regardless of Nimbus enrollment.

        Gating sections response on enrollment caused the Ireland incident where an experiment
        gate was forgotten and clients kept receiving the wrong treatment. Sections branches in
        sections-in-germany-v2 are differentiated from control by what the client requests, not
        by a backend gate.
        """
        request = CuratedRecommendationsRequest(
            locale="de-DE",
            feeds=["sections"],
            experimentName=experiment_name,
            experimentBranch=experiment_branch,
        )
        assert (
            CuratedRecommendationsProvider.is_sections_experiment(request, SurfaceId.NEW_TAB_DE_DE)
            is True
        )

    def test_de_without_sections_feed_returns_false(self):
        """If the client does not request sections, the response is not sections."""
        request = CuratedRecommendationsRequest(
            locale="de-DE",
            feeds=None,
            experimentName="sections-in-germany-v2",
            experimentBranch="content-only",
        )
        assert (
            CuratedRecommendationsProvider.is_sections_experiment(request, SurfaceId.NEW_TAB_DE_DE)
            is False
        )
