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
    )  # this needs to be very high. We aren't using it and it shouldn't be invoked
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
    assert model.get_unary_encoded_index("") is None


def test_model_matches_interests(model_limited):
    """Check model id's match"""
    model = model_limited.get(TEST_SURFACE)

    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    assert model.model_matches_interests(interests.root[LOCAL_MODEL_MODEL_ID_KEY])


def test_model_no_match_interests(model_limited):
    """Check model id's don't match"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = "bad id"
    assert not model.model_matches_interests(interests.root[LOCAL_MODEL_MODEL_ID_KEY])


def test_decode_dp_interests_ambiguous(model_limited):
    """Verify ambiguous interests due to noise"""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    values = []
    for model_key, model_feature_info in model.model_data.interest_vector.items():
        values.append("1" * (len(model_feature_info.thresholds) + 1))  # concat a string
    interests.root["values"] = values
    updated_inferred_interests = model.decode_dp_interests(
        interests.root["values"], interests.root[LOCAL_MODEL_MODEL_ID_KEY]
    )
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
    updated_inferred_interests = model.decode_dp_interests(
        interests.root["values"], interests.root[LOCAL_MODEL_MODEL_ID_KEY]
    )
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
    updated_inferred_interests = model.decode_dp_interests(
        interests.root["values"], interests.root[LOCAL_MODEL_MODEL_ID_KEY]
    )
    for idx, (model_key, model_feature_info) in enumerate(
        model.model_data.interest_vector.items()
    ):
        assert updated_inferred_interests[model_key] == model_feature_info.thresholds[-1]


def test_decode_skipped_when_model_id_mismatch(model_limited):
    """Caller should not decode when the model id doesn't match."""
    model = model_limited.get("surface")
    wrong_id = "not-this-model"
    assert not model.model_matches_interests(wrong_id)


def test_model_matches_interests_none_and_non_str(model_limited):
    """Ensure model_matches_interests rejects None and non-string ids."""
    model = model_limited.get(TEST_SURFACE)
    assert not model.model_matches_interests(None)
    assert not model.model_matches_interests(3.14159)  # float should not match


def test_unary_random_if_uncertain_when_no_ones(model_limited):
    """When there are no '1' bits and random_if_uncertain=True, returns 0."""
    model = model_limited.get(TEST_SURFACE)
    assert model.get_unary_encoded_index("0000", random_if_uncertain=True) == 0


def test_decode_dp_interests_random_choice_sets_key(model_limited):
    """With multiple '1' bits and random_if_uncertain=True, we still decode to an allowed value
    (either 0.0 for index 0 or the corresponding threshold for the chosen index).
    """
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector

    dp_values = []
    first_key = next(iter(iv.keys()))
    first_cfg = iv[first_key]
    for i, (_k, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if i == 0:
            dp_values.append("1010" if n >= 4 else "11")  # multiple ones
        else:
            dp_values.append("0" * (n - 1) + "1")  # deterministic high

    np.random.seed(123)
    out = model.decode_dp_interests(dp_values, model.model_id, random_if_uncertain=True)
    allowed = {0.0, first_cfg.thresholds[1]} if len(first_cfg.thresholds) >= 2 else {0.0}
    assert first_key in out
    assert out[first_key] in allowed


def test_decode_dp_interests_empty_list_raises(model_limited):
    """Empty dp_values should raise due to direct indexing in decode."""
    model = model_limited.get(TEST_SURFACE)
    with pytest.raises(IndexError):
        model.decode_dp_interests([], model.model_id)
