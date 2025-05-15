"""Unit tests for fake local model"""

import pytest
from merino.curated_recommendations.ml_backends.fake_local_model import (
    FakeLocalModel,
    FAKE_MODEL_ID,
)
from merino.curated_recommendations.ml_backends.protocol import InferredLocalModel


@pytest.fixture
def model():
    """Create fake model"""
    return FakeLocalModel()


def test_model_returns_inferred_local_model(model):
    """Tests fake local model"""
    surface_id = "test_surface"
    result = model.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.model_id == FAKE_MODEL_ID
    assert result.surface_id == surface_id
    assert isinstance(result.model_data, dict)
