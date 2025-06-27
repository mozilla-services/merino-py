"""Unit tests for fake local model"""

import pytest
from merino.curated_recommendations.ml_backends.fake_local_model import (
    FakeLocalModelTopics,
    FakeLocalModelSections,
    CTR_TOPIC_MODEL_ID,
)
from merino.curated_recommendations.ml_backends.protocol import InferredLocalModel


@pytest.fixture
def model_topics():
    """Create fake model"""
    return FakeLocalModelTopics()


def test_model_returns_inferred_local_model_topics(model_topics):
    """Tests fake local model, topics"""
    surface_id = "test_surface"
    result = model_topics.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.model_id == CTR_TOPIC_MODEL_ID
    assert result.surface_id == surface_id
    assert result.model_version == 0
    assert result.model_data is not None
    assert result.model_data.noise_scale > 0
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0


@pytest.fixture
def model_sections():
    """Create fake model"""
    return FakeLocalModelSections()


def test_model_returns_inferred_local_model_sections(model_sections):
    """Tests fake local model, sections"""
    surface_id = "test_surface"
    result = model_sections.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.model_id == CTR_TOPIC_MODEL_ID
    assert result.surface_id == surface_id
    assert result.model_version == 0
    assert result.model_data is not None
    assert result.model_data.noise_scale > 0
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0
