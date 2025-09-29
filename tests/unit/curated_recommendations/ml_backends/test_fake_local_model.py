"""Unit tests for fake local model"""

import numpy as np
import pytest
from types import SimpleNamespace

from merino.curated_recommendations.corpus_backends.protocol import Topic
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
from merino.curated_recommendations.protocol import InferredInterests, ProcessedInterests

from merino.curated_recommendations.provider import (
    CuratedRecommendationsProvider,
    LOCAL_MODEL_DB_VALUES_KEY,
)

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
        result.model_data.noise_scale == 0.0
    )  # This needs to be 0 if we use coarse threshold based vector.
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0

    # test a specific threshold value
    assert result.model_data.interest_vector[Topic.SPORTS.value].thresholds[0] == 0.005


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


def test_decode_sets_model_id_in_result(model_limited):
    """decode_dp_interests sets the model_id in the returned dict."""
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector
    # Make a valid dp_values list: choose the highest index for each feature.
    dp_values = []
    for _k, cfg in iv.items():
        n = len(cfg.thresholds) + 1
        dp_values.append("0" * (n - 1) + "1")
    out = model.decode_dp_interests(dp_values, model.model_id)
    assert out[LOCAL_MODEL_MODEL_ID_KEY] == model.model_id


def test_decode_uses_middle_threshold_when_index_is_one_based(model_limited):
    """decode_dp_interests maps index>0 to thresholds[index-1] (check middle index)."""
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector
    first_key = next(iter(iv.keys()))
    first_cfg = iv[first_key]
    # Build dp_values so first feature uses index 2 (-> thresholds[1]); others pick last.
    dp_values = []
    for i, (_k, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if i == 0:
            # index 2 -> "0010" when n==4; general form:
            index = 2
            dp_values.append("0" * index + "1" + "0" * (n - 1 - index))
        else:
            dp_values.append("0" * (n - 1) + "1")
    out = model.decode_dp_interests(dp_values, model.model_id)
    assert out[first_key] == first_cfg.thresholds[1]


def test_decode_treats_nonzero_char_as_one(model_limited):
    """Non-'0' characters are treated as '1' during unary decoding."""
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector
    first_key = next(iter(iv.keys()))
    first_cfg = iv[first_key]
    dp_values = []
    for i, (_k, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if i == 0:
            # '0a00' -> index 1 (since 'a' is treated as '1')
            if n >= 4:
                dp_values.append("0a00")
            else:
                # fallback for smaller n: put 'a' at index 1
                dp_values.append("0a" + "0" * (n - 2))
        else:
            dp_values.append("0" * (n - 1) + "1")
    out = model.decode_dp_interests(dp_values, model.model_id)
    assert out[first_key] == first_cfg.thresholds[0]


def test_model_matches_interests_rejects_none_and_float(model_limited):
    """model_matches_interests should reject None and non-string values."""
    model = model_limited.get(TEST_SURFACE)
    assert not model.model_matches_interests(None)
    assert not model.model_matches_interests(3.14)


def test_decode_with_multiple_ones_random_branch_sets_valid_value(model_limited):
    """With multiple '1's and random_if_uncertain=True, decoded value is within allowed set."""
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector
    first_key = next(iter(iv.keys()))
    first_cfg = iv[first_key]
    dp_values = []
    for i, (_k, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if i == 0:
            # multiple ones at indices 0 and 2 (requires n>=3); otherwise use "11"
            dp_values.append("1010" if n >= 4 else "11")
        else:
            dp_values.append("0" * (n - 1) + "1")
    np.random.seed(123)
    out = model.decode_dp_interests(dp_values, model.model_id, random_if_uncertain=True)
    allowed = {0.0}
    if len(first_cfg.thresholds) >= 2:
        allowed.add(first_cfg.thresholds[1])
    assert first_key in out
    assert out[first_key] in allowed


@pytest.mark.parametrize(
    "pattern_func,assertion_func,rand",
    [
        # ambiguous: all ones; no random -> key not present
        (
            lambda thresholds: "1" * (len(thresholds) + 1),
            lambda result, key, thresholds: key not in result,
            False,
        ),
        # lowest value (index 0) -> 0.0
        (
            lambda thresholds: "1" + "0" * len(thresholds),
            lambda result, key, thresholds: result[key] == 0.0,
            False,
        ),
        # highest value (last index) -> thresholds[-1]
        (
            lambda thresholds: "0" * len(thresholds) + "1",
            lambda result, key, thresholds: result[key] == thresholds[-1],
            False,
        ),
        # middle value: pick index 2 if available, else 1, else 0
        (
            lambda thresholds: (
                (lambda i, n: "0" * i + "1" + "0" * (n - 1 - i))(
                    2 if len(thresholds) >= 2 else (1 if len(thresholds) == 1 else 0),
                    len(thresholds) + 1,
                )
            ),
            lambda result, key, thresholds: (
                result[key]
                == (
                    0.0
                    if (2 if len(thresholds) >= 2 else (1 if len(thresholds) == 1 else 0)) == 0
                    else thresholds[
                        (2 if len(thresholds) >= 2 else (1 if len(thresholds) == 1 else 0)) - 1
                    ]
                )
            ),
            False,
        ),
        # ambiguous with random -> value is allowed (0.0 or any threshold)
        (
            lambda thresholds: "1" * (len(thresholds) + 1),
            lambda result, key, thresholds: key in result
            and result[key] in ({0.0} | set(thresholds)),
            True,
        ),
    ],
    ids=[
        "ambiguous_no_random",
        "lowest",
        "highest",
        "middle",
        "ambiguous_with_random",
    ],
)
def test_decode_dp_interests(model_limited, pattern_func, assertion_func, rand):
    """decode_dp_interests decodes various unary patterns; ambiguous behavior depends on random flag."""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID

    values = []
    for _key, feature in model.model_data.interest_vector.items():
        values.append(pattern_func(feature.thresholds))
    interests.root["values"] = values

    if rand:
        np.random.seed(123)
    updated = model.decode_dp_interests(
        interests.root["values"],
        interests.root[LOCAL_MODEL_MODEL_ID_KEY],
        random_if_uncertain=rand,
    )

    for key, feature in model.model_data.interest_vector.items():
        assert assertion_func(updated, key, feature.thresholds)


@pytest.mark.parametrize(
    "input_id,expected",
    [
        (CTR_LIMITED_TOPIC_MODEL_ID, True),
        ("bad id", False),
        (None, False),
        (3.14, False),
    ],
)
def test_model_matches_interests_param(model_limited, input_id, expected):
    """model_matches_interests accepts only the correct string id."""
    model = model_limited.get(TEST_SURFACE)
    assert model.model_matches_interests(input_id) is expected


@pytest.fixture
def inferred_model():
    """Build a concrete InferredLocalModel for tests."""
    backend = LimitedTopicV0Model()
    return backend.get("surface")


def make_request(interests: InferredInterests | None):
    """Return a minimal request-like object carrying inferredInterests."""
    return SimpleNamespace(inferredInterests=interests)


def test_process_returns_none_when_request_has_no_interests(inferred_model):
    """If request.inferredInterests is None, return None."""
    req = make_request(None)
    out = CuratedRecommendationsProvider.process_request_interests(req, inferred_model)
    assert out is None


def test_process_passes_through_when_no_model():
    """When inferred_local_model is None, return ProcessedInterests with empty scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    req = make_request(interests)
    out = CuratedRecommendationsProvider.process_request_interests(req, inferred_local_model=None)
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == CTR_LIMITED_TOPIC_MODEL_ID
    assert out.scores == {}


def test_process_passes_through_on_model_id_mismatch(inferred_model):
    """When model_id doesn't match, return ProcessedInterests with empty scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = "not-this-model"
    interests.root["foo"] = "bar"  # String value, not a score
    req = make_request(interests)
    out = CuratedRecommendationsProvider.process_request_interests(req, inferred_model)
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == "not-this-model"
    assert out.scores == {}  # String values are not included in scores


def test_process_decodes_when_values_present(inferred_model):
    """When model_id matches and values are present, decode into floats."""
    # Build a valid dp_values array aligned with the model's interest_vector order
    iv = inferred_model.model_data.interest_vector
    dp_values = []
    for _key, cfg in iv.items():
        n = len(cfg.thresholds) + 1
        dp_values.append("0" * (n - 1) + "1")  # choose highest index for determinism

    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    interests.root[LOCAL_MODEL_DB_VALUES_KEY] = dp_values
    req = make_request(interests)

    out = CuratedRecommendationsProvider.process_request_interests(req, inferred_model)
    assert isinstance(out, ProcessedInterests)
    # model_id is preserved
    assert out.model_id == CTR_LIMITED_TOPIC_MODEL_ID

    # spot-check a couple of features decode to the last threshold
    checked = 0
    for key, cfg in iv.items():
        assert out.scores[key] == cfg.thresholds[-1]
        checked += 1
        if checked >= 2:
            break


def test_process_passthrough_when_values_missing_even_with_matching_model(inferred_model):
    """If model_id matches but no DP values key, extract existing numeric scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = CTR_LIMITED_TOPIC_MODEL_ID
    interests.root["foo"] = 0.123
    interests.root["bar"] = "baz"  # String, not a score
    req = make_request(interests)

    out = CuratedRecommendationsProvider.process_request_interests(req, inferred_model)
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == CTR_LIMITED_TOPIC_MODEL_ID
    assert out.scores["foo"] == 0.123
    assert "bar" not in out.scores  # String values are not included in scores
