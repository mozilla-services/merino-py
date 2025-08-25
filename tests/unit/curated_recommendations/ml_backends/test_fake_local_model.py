"""Unit tests for fake local model"""

import numpy as np
import pytest
from merino.curated_recommendations.ml_backends.fake_local_model import (
    FakeLocalModelTopics,
    FakeLocalModelSections,
    LimitedTopicV0Model,
    CTR_TOPIC_MODEL_ID,
    CTR_SECTION_MODEL_ID,
    CTR_LIMITED_TOPIC_MODEL_ID,
)
from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    LOCAL_MODEL_MODEL_ID_KEY,
)
from merino.curated_recommendations.protocol import InferredInterests

TEST_SURFACE = "test_surface"


@pytest.fixture
def model_topics():
    """Create fake model"""
    return FakeLocalModelTopics()


@pytest.fixture
def model_limited():
    """Create fake model"""
    return LimitedTopicV0Model()


def test_model_returns_inferred_local_model_topics(model_topics):
    """Tests fake local model, topics"""
    surface_id = TEST_SURFACE
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
    surface_id = TEST_SURFACE
    result = model_sections.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.model_id == CTR_SECTION_MODEL_ID
    assert result.surface_id == surface_id
    assert result.model_version == 0
    assert result.model_data is not None
    assert result.model_data.noise_scale > 0
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0


def test_model_returns_limited_model(model_limited):
    """Tests fake local model, sections"""
    surface_id = TEST_SURFACE
    result = model_limited.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.surface_id == surface_id
    assert result.model_id == CTR_LIMITED_TOPIC_MODEL_ID
    assert result.model_version == 0
    assert result.model_data is not None
    assert (
        result.model_data.noise_scale >= 0.02
    )  # this needs to be very high. We aren't using it and it shouln't be invokedd
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0


def test_unary_decoding(model_limited):
    """Test unary decoding of interest found interest vector values func"""
    # "00100" -> index 2
    model = model_limited.get(TEST_SURFACE)

    assert model.get_unary_encoded_index("00100") == 2
    # Multiple 1s and random_if_uncertain == False => None
    assert model.get_unary_encoded_index("01101", random_if_uncertain=False) is None
    # Make randomness deterministic
    np.random.seed(123)
    encoded = "01011"  # candidates at indices 1,3,4
    idx = model.get_unary_encoded_index(encoded, random_if_uncertain=True)
    assert idx in {1, 3, 4}
    # non-"0" characters are treated as "1"
    assert model.get_unary_encoded_index("0a00") == 1
    assert model.get_unary_encoded_index("0000") is None


def test_model_matches_interests(model_limited):
    """Check model id's match"""
    model = model_limited.get(TEST_SURFACE)

    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    assert model.model_matches_interests(interests.root)


def test_model_no_match_interests(model_limited):
    """Check model id's don't match"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = "bad id"
    assert not model.model_matches_interests(interests.root)


def test_decode_dp_interests_ambiguous(model_limited):
    """Verify ambiguous interests due to noise"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    values = []
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        values.append("1" * (len(model_feature_info.thresholds) + 1))  # concat a string
    interests.root["values"] = values
    updated_inferred_interests = model.decode_dp_interests(interests.root)
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        assert model_key not in updated_inferred_interests


def test_decode_dp_interests_low(model_limited):
    """Verify the lowest CTR is decoded"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    values = []
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        values.append("1" + "0" * len(model_feature_info.thresholds))  # concat a string
    interests.root["values"] = values
    updated_inferred_interests = model.decode_dp_interests(interests.root)
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        assert updated_inferred_interests[model_key] == 0.0


def test_decode_dp_interests_high(model_limited):
    """Verify highest thresholded CTR is decoded"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    values = []
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        values.append("0" * len(model_feature_info.thresholds) + "1")  # concat a string
    interests.root["values"] = values
    updated_inferred_interests = model.decode_dp_interests(interests.root)
    for idx, (model_key, model_feature_info) in enumerate(
        model.model_data.interest_vector.items()
    ):
        assert updated_inferred_interests[model_key] == model_feature_info.thresholds[-1]


def test_decode_raises_on_wrong_model_id(model_limited):
    """Decode should raise if model IDs do not match."""
    model = model_limited.get("surface")
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = "not-this-model"
    with pytest.raises(Exception):
        model.decode_dp_interests(interests.root)


def test_decode_raises_when_values_not_list(model_limited):
    """If 'values' exists but is not a list -> raise."""
    model = model_limited.get("surface")
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = model.model_id
    interests.root["values"] = "oops-not-a-list"
    with pytest.raises(Exception):
        model.decode_dp_interests(interests.root)


def test_decode_returns_flat_when_no_values(model_limited):
    """If there are no DP values, decode_dp_interests should return the same flat dict."""
    model = model_limited.get("surface")
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = model.model_id
    # add some already-decoded floats/strings
    interests.root["foo"] = 0.123
    interests.root["bar"] = "baz"

    out = model.decode_dp_interests(interests.root)
    assert out["foo"] == 0.123
    assert out["bar"] == "baz"
    assert out[LOCAL_MODEL_MODEL_ID_KEY] == model.model_id


def test_decode_raises_on_length_mismatch(model_limited):
    """If the number of unary strings doesn't match the configured interest_vector -> raise."""
    model = model_limited.get("surface")
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = model.model_id
    # Provide fewer unary strings than interest_vector entries to force the mismatch path
    interests.root["values"] = ["1"]  # definitely shorter than configured vector
    with pytest.raises(Exception):
        model.decode_dp_interests(interests.root)
