"""Unit tests for static local model"""

import math

import pytest
from types import SimpleNamespace

from merino.curated_recommendations.corpus_backends.protocol import Topic, SurfaceId
from merino.curated_recommendations.ml_backends.static_local_model import (
    SERVER_V3_MODEL_ID,
    THRESHOLDS_V3_NORMALIZED,
    FakeLocalModelSections,
    SuperInferredModel,
    CTR_SECTION_MODEL_ID,
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

from merino.curated_recommendations.protocol import ExperimentName

INFERRED_V3_EXPERIMENT_NAME = ExperimentName.INFERRED_LOCAL_EXPERIMENT_V3.value

TEST_SURFACE = "test_surface"


@pytest.fixture
def model_limited():
    """Create static model"""
    return SuperInferredModel()


@pytest.fixture
def local_model_backend():
    """Create static model  - used for more generic tests than model_limited"""
    return SuperInferredModel()


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


def test_model_returns_default_limited_model(model_limited):
    """Tests fake local model"""
    surface_id = TEST_SURFACE
    result = model_limited.get(surface_id)

    assert isinstance(result, InferredLocalModel)
    assert result.surface_id == surface_id
    assert result.model_id == SERVER_V3_MODEL_ID
    assert result.model_version == 0
    assert result.model_data is not None
    assert (
        result.model_data.noise_scale == 0.0
    )  # This needs to be 0 if we use coarse threshold based vector.
    assert len(result.model_data.interest_vector) > 0
    assert len(result.model_data.day_time_weighting.days) > 0
    assert len(result.model_data.day_time_weighting.relative_weight) > 0

    # test a specific threshold value
    assert (
        result.model_data.interest_vector[Topic.SPORTS.value].thresholds[0]
        == THRESHOLDS_V3_NORMALIZED[0]
    )


def test_model_returns_no_model_when_unsupported(model_limited):
    """Tests fake local model"""
    surface_id = TEST_SURFACE
    result = model_limited.get(surface_id, model_id="obsolete_model")
    assert result is None


def test_unary_decoding(model_limited):
    """Test unary decoding of interest found interest vector values func"""
    # "00100" -> index 2
    model = model_limited.get(TEST_SURFACE)

    assert model.get_unary_encoded_index("00100") == [2]

    # Test too many oness
    assert model.get_unary_encoded_index("01101", support_two=False) == []
    assert model.get_unary_encoded_index("01101", support_two=True) == []

    # Test support for two results
    encoded = "01010"  # candidates at indices 1,3,4
    idx = model.get_unary_encoded_index(encoded, support_two=True)
    assert idx == [1, 3]
    # Test support for two results
    encoded = "01010"  # candidates at indices 1,3,4
    assert model.get_unary_encoded_index(encoded, support_two=False) == []

    # non-"0" characters are treated as "1" and empty case
    assert model.get_unary_encoded_index("0a00") == [1]
    assert model.get_unary_encoded_index("0000") == []
    assert model.get_unary_encoded_index("") == []


def test_decode_skipped_when_model_id_mismatch(model_limited):
    """Caller should not decode when the model id doesn't match."""
    model = model_limited.get("surface")
    wrong_id = "not-this-model"
    assert not model.model_matches_interests(wrong_id)


def test_model_experiment_name_and_branch_name(model_limited):
    """Caller should not decode when the model id doesn't match."""
    model = model_limited.get(
        "surface",
        experiment_name=INFERRED_V3_EXPERIMENT_NAME,
        experiment_branch="any",
    )
    assert model.model_matches_interests(SERVER_V3_MODEL_ID)
    assert (
        len(model.model_data.private_features) > 0 and len(model.model_data.private_features) <= 8
    )


def test_model_matches_interests_none_and_non_str(model_limited):
    """Ensure model_matches_interests rejects None and non-string ids."""
    model = model_limited.get(TEST_SURFACE)
    assert not model.model_matches_interests(None)
    assert not model.model_matches_interests(3.14159)  # float should not match


def test_unary_when_no_ones(model_limited):
    """When there are no '1' bits and returns no items."""
    model = model_limited.get(TEST_SURFACE)
    assert model.get_unary_encoded_index("0000", support_two=True) == []


def test_decode_dp_interests_passes_no_private(model_limited):
    """Empty dp_values should not raise due to direct indexing in decode.
    this is not true when private_features=[]
    """
    model = model_limited.get(TEST_SURFACE)
    model.model_data.private_features = []
    result = model.decode_dp_interests("1000", model.model_id)
    assert len(result.keys()) == 1  ## 1 key is model_id
    assert "model_id" in result


def test_decode_dp_interests_passes_one_private(model_limited):
    """If we set one private interest, we get one back"""
    model = model_limited.get(TEST_SURFACE)
    model.model_data.private_features = ["arts"]
    result = model.decode_dp_interests("1000", model.model_id)
    ## if model changes to exclude arts, this should be changed in PR
    assert "arts" in model.model_data.interest_vector
    ## 1 key is model_id , second is arts
    assert len(result.keys()) == 2
    ## we get out arts still
    assert "arts" in result
    assert "model_id" in result


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


def test_decode_with_multiple_ones_sets_valid_value(model_limited):
    """With multiple '1's decoded value is as expected."""
    model = model_limited.get(TEST_SURFACE)
    iv = model.model_data.interest_vector
    first_key = next(iter(iv.keys()))
    first_cfg = iv[first_key]
    dp_values = []
    for i, (_k, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if i == 0:
            # multiple ones at indices 0 and 1
            dp_values.append("11" + "0" * (n - 2))
        else:
            dp_values.append("0" * (n - 1) + "1")
    out = model.decode_dp_interests(dp_values, model.model_id)
    assert first_key in out
    assert out[first_key] == (0.0 + first_cfg.thresholds[0]) * 0.5


@pytest.mark.parametrize(
    "pattern_func,assertion_func,support_two",
    [
        # Two values allowed
        (
            lambda thresholds: "011" + (len(thresholds) - 2) * "0",
            lambda result, key, thresholds: result[key] == (thresholds[0] + thresholds[1]) * 0.5,
            True,
        ),
        # two values not allowed
        (
            lambda thresholds: "011" + (len(thresholds) - 2) * "0",
            lambda result, key, thresholds: key not in result,
            False,
        ),
        # All values set
        (
            lambda thresholds: "1" * (len(thresholds) + 1),
            lambda result, key, thresholds: key not in result,
            True,
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
    ],
    ids=[
        "two_values_allowed",
        "two_values_not_allowed",
        "all_values_set",
        "lowest",
        "highest",
        "middle",
    ],
)
def test_decode_dp_interests(model_limited, pattern_func, assertion_func, support_two):
    """decode_dp_interests decodes various unary patterns."""
    model = model_limited.get(TEST_SURFACE)
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = SERVER_V3_MODEL_ID

    values = []
    for _key, feature in model.model_data.interest_vector.items():
        values.append(pattern_func(feature.thresholds))
    interests.root["values"] = values

    updated = model.decode_dp_interests(
        interests.root["values"],
        interests.root[LOCAL_MODEL_MODEL_ID_KEY],
        support_two=support_two,
    )

    for key, feature in model.model_data.interest_vector.items():
        assert assertion_func(updated, key, feature.thresholds)


@pytest.mark.parametrize(
    "input_id,expected",
    [
        (SERVER_V3_MODEL_ID, True),
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
    backend = SuperInferredModel()
    return backend.get("surface")


def make_request(interests: InferredInterests | None):
    """Return a minimal request-like object carrying inferredInterests."""
    return SimpleNamespace(inferredInterests=interests, experimentName=None, experimentBranch=None)


def test_process_returns_none_when_request_has_no_interests(inferred_model, local_model_backend):
    """If request.inferredInterests is None, return None."""
    req = make_request(None)
    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert out is None


def test_process_passes_through_when_no_model(local_model_backend):
    """When inferred_local_model is None, return ProcessedInterests with empty scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = SERVER_V3_MODEL_ID
    req = make_request(interests)
    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == SERVER_V3_MODEL_ID
    assert out.scores == {}
    assert out.normalized_scores == {}


def test_process_passes_through_on_model_id_mismatch(inferred_model, local_model_backend):
    """When model_id doesn't match, return ProcessedInterests with empty scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = "not-this-model"
    interests.root["foo"] = "bar"  # String value, not a score
    req = make_request(interests)
    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == "not-this-model"
    assert out.scores == {}  # String values are not included in scores
    assert out.normalized_scores == {}


def test_process_decodes_when_same_values_present(inferred_model, local_model_backend):
    """When model_id matches and values are present, decode into floats."""
    # Build a valid dp_values array aligned with the model's interest_vector order
    iv = inferred_model.model_data.interest_vector
    dp_values = []
    for _key, cfg in iv.items():
        n = len(cfg.thresholds) + 1
        dp_values.append("0" * (n - 1) + "1")  # choose highest index for determinism

    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = SERVER_V3_MODEL_ID
    interests.root[LOCAL_MODEL_DB_VALUES_KEY] = dp_values
    req = make_request(interests)

    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert isinstance(out, ProcessedInterests)
    # model_id is preserved
    assert out.model_id == SERVER_V3_MODEL_ID

    # spot-check a couple of features decode to the last threshold
    for key, cfg in iv.items():
        assert out.scores[key] == cfg.thresholds[-1]
        assert abs(out.normalized_scores[key] - 1 / math.sqrt(len(iv))) < 0.01  # normalized


def test_process_decodes_when_different_present(inferred_model, local_model_backend):
    """When model_id matches and values are present, decode into floats."""
    # Build a valid dp_values array aligned with the model's interest_vector order
    iv = inferred_model.model_data.interest_vector
    dp_values = []
    for idx, (_key, cfg) in enumerate(iv.items()):
        n = len(cfg.thresholds) + 1
        if idx == 0:
            dp_values.append("0" * (n - 1) + "1")  # choose highest index for determinism
        else:
            dp_values.append("1" + (n - 1) * "0")  # lowest (0) value

    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = SERVER_V3_MODEL_ID
    interests.root[LOCAL_MODEL_DB_VALUES_KEY] = dp_values
    req = make_request(interests)

    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert isinstance(out, ProcessedInterests)
    # model_id is preserved
    assert out.model_id == SERVER_V3_MODEL_ID
    # spot-check a couple of features decode to the last threshold
    for idx, (key, cfg) in enumerate(iv.items()):
        if idx == 0:
            assert out.scores[key] == cfg.thresholds[-1]
            assert abs(out.normalized_scores[key] - 1) < 0.01  # normalizes to 1
        else:
            assert out.scores[key] == 0.0
            assert abs(out.normalized_scores[key]) < 0.01  # normalizes to 0


def test_process_passthrough_when_values_missing_even_with_matching_model(
    inferred_model, local_model_backend
):
    """If model_id matches but no DP values key, extract existing numeric scores."""
    interests = InferredInterests.empty()
    interests.root[LOCAL_MODEL_MODEL_ID_KEY] = SERVER_V3_MODEL_ID
    interests.root["foo"] = 0.123
    interests.root["bar"] = "baz"  # String, not a score
    req = make_request(interests)

    out = CuratedRecommendationsProvider.process_request_interests(
        req, SurfaceId.NEW_TAB_EN_US, local_model_backend
    )
    assert isinstance(out, ProcessedInterests)
    assert out.model_id == SERVER_V3_MODEL_ID
    assert out.scores["foo"] == 0.123
    assert "bar" not in out.normalized_scores  # String values are not included in scores
    assert "bar" not in out.scores  # String values are not included in scores


@pytest.mark.parametrize(
    "experiment,branch,model_id,expect_private_nonempty",
    [
        (
            "optin-" + INFERRED_V3_EXPERIMENT_NAME,
            "any_branch",
            SERVER_V3_MODEL_ID,
            True,
        ),
        (
            INFERRED_V3_EXPERIMENT_NAME,
            "any_branch",
            SERVER_V3_MODEL_ID,
            True,
        ),
        (
            "sdfs",
            "any_branch",
            SERVER_V3_MODEL_ID,
            True,
        ),
    ],
)
def test_get_with_experiment_and_model_id_correct_branch_returns_model(
    model_limited, experiment, branch, model_id, expect_private_nonempty
):
    """When passing a model_id for the experiment AND the correct branch, return that model."""
    result = model_limited.get(
        TEST_SURFACE,
        model_id=model_id,
        experiment_name=experiment,
        experiment_branch=branch,
    )

    assert isinstance(result, InferredLocalModel)
    assert result.model_id is not None
    # sanity checks on payload
    assert result.surface_id == TEST_SURFACE
    assert result.model_data is not None
    assert isinstance(result.model_data.interest_vector, dict)
    # private features presence depends on branch
    if expect_private_nonempty:
        assert result.model_data.private_features and len(result.model_data.private_features) > 0
    else:
        assert result.model_data.private_features == []


def test_get_dummy_experiment_name(model_limited):
    """Control check: an unknown experiment name and no model_id defaults to no model."""
    result = model_limited.get(
        TEST_SURFACE,
        model_id=None,
        experiment_name="moo",
        experiment_branch="cow",
    )
    assert result is not None
    assert result.model_id == SERVER_V3_MODEL_ID
    assert isinstance(result, InferredLocalModel)
    # basic payload sanity
    assert Topic.SPORTS.value in result.model_data.interest_vector
