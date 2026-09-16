"""Coverage for CTR prediction treatment scoring and request routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, SectionsProtocol
from merino.curated_recommendations.prior_backends.constant_prior import ConstantPrior
from merino.curated_recommendations.prior_backends.protocol import EngagementRescaler
from merino.curated_recommendations.protocol import CuratedRecommendationsRequest
from merino.curated_recommendations.rankers import ctr_prediction
from merino.curated_recommendations.rankers.t_sampling import ThompsonSamplingRanker
from merino.curated_recommendations.sections import get_sections
from merino.curated_recommendations.utils import derive_engagement_region
from tests.unit.curated_recommendations.fixtures import (
    generate_recommendations,
    generate_sections_feed,
)
from tests.unit.curated_recommendations.test_rankers import RegionAwareStubEngagementBackend
from tests.unit.curated_recommendations.test_sections import generate_corpus_section


@pytest.mark.parametrize("name", ["ctrpred_engb", "optin-ctrpred_engb", "unrelated", None])
@pytest.mark.parametrize("branch", ["treatment", "control", "other", None])
@pytest.mark.parametrize("locale,region", [("en-GB", "GB"), ("en-US", "US"), ("de-DE", "GB")])
@pytest.mark.asyncio
async def test_experiment_routing(name, branch, locale, region, mocker):
    """Only enrolled en_GB requests get branch data and the treatment ranker."""
    from merino.curated_recommendations.utils import get_recommendation_surface_id

    request = CuratedRecommendationsRequest(
        locale=locale, region=region, experimentName=name, experimentBranch=branch
    )
    surface = get_recommendation_surface_id(request.locale, region, request)
    enrolled = (
        surface == SurfaceId.NEW_TAB_EN_GB
        and name in {"ctrpred_engb", "optin-ctrpred_engb"}
        and branch in {"control", "treatment"}
    )
    engagement_region = derive_engagement_region(request)
    assert engagement_region == (f"GB-ctrpred_engb-{branch}" if enrolled else region)
    treatment_items = mocker.spy(ctr_prediction.CTRPredictionRanker, "rank_items")
    treatment_sections = mocker.spy(ctr_prediction.CTRPredictionRanker, "rank_sections")
    vanilla_items = mocker.spy(ThompsonSamplingRanker, "rank_items")
    vanilla_sections = mocker.spy(ThompsonSamplingRanker, "rank_sections")
    backend = MagicMock(spec=SectionsProtocol)
    backend.fetch = AsyncMock(return_value=[generate_corpus_section("business", count=12)])
    ml = MagicMock()
    ml.is_valid.return_value = False
    await get_sections(
        request=request,
        surface_id=surface,
        sections_backend=backend,
        ml_backend=ml,
        engagement_backend=RegionAwareStubEngagementBackend({}),
        prior_backend=ConstantPrior(),
        lints_interest_backend=ml,
        region=region,
        engagement_region=engagement_region,
    )
    treatment = enrolled and branch == "treatment"
    assert treatment_items.call_count == int(treatment)
    assert treatment_sections.call_count == int(treatment)
    assert vanilla_items.call_count == int(not treatment)
    assert vanilla_sections.call_count == int(not treatment)


@pytest.mark.parametrize("hour", [0, 12, 23])
def test_missing_rows_use_hourly_fallback_not_country_counts(hour, monkeypatch):
    """Even an entirely missing branch must not consume raw GB engagement."""
    monkeypatch.setattr(ctr_prediction, "PSEUDOCOUNT_UTC_HOUR_OVERRIDE", hour)
    backend = RegionAwareStubEngagementBackend({("item", "GB"): (900, 1000)})
    ranker = ctr_prediction.CTRPredictionRanker(backend, ConstantPrior())
    recs = generate_recommendations(item_ids=["item"])
    ranker.rank_items(recs, region="GB", engagement_region="GB-ctrpred_engb-treatment")
    data = recs[0].ranking_data
    expected = ctr_prediction.ACTRSSM_CONSTANTS_BY_REGION["GB"]["hourly_ctr"][hour]
    assert data.alpha / (data.alpha + data.beta) == pytest.approx(expected)
    assert ("item", "GB") not in backend.calls


def test_existing_rows_and_fractional_freshness():
    """Treatment uses counts without additive priors and marks the lowest eighth fresh."""
    region = "GB-ctrpred_engb-treatment"
    recs = generate_recommendations(item_ids=[str(i) for i in range(16)], time_sensitive_count=0)
    backend = RegionAwareStubEngagementBackend({(str(i), region): (2, 20 + i) for i in range(16)})
    ranker = ctr_prediction.CTRPredictionRanker(backend, ConstantPrior())
    ranker.rank_items(recs, region="GB", engagement_region=region, rescaler=EngagementRescaler())
    for i, rec in enumerate(recs):
        assert rec.ranking_data.alpha == 2
        assert rec.ranking_data.beta == 18 + i
        assert rec.ranking_data.is_fresh == (i < 2)


def test_section_scores_sum_pseudocounts(mocker):
    """Section sampling adds pseudo-counts without the legacy section prior."""
    sections = generate_sections_feed(section_count=1)
    sections["top_stories_section"].recommendations = generate_recommendations(length=3)
    region = "GB-ctrpred_engb-treatment"
    backend = RegionAwareStubEngagementBackend(
        {
            (rec.corpusItemId, region): (2, 20)
            for section in sections.values()
            for rec in section.recommendations
        }
    )
    sample = mocker.patch.object(ctr_prediction.beta, "rvs", return_value=0.5)
    ranker = ctr_prediction.CTRPredictionRanker(backend, ConstantPrior())
    ranker.rank_sections(sections, region="GB", engagement_region=region)
    sample.assert_called_once_with(6.0, 54.0)


@pytest.mark.parametrize("clicks,impressions,alpha,beta", [(0, 10, 1e-18, 10), (5, 3, 5, 1e-18)])
def test_existing_nonempty_or_inconsistent_rows(clicks, impressions, alpha, beta):
    """Existing rows keep their pseudo-counts, clamped to valid beta parameters."""
    backend = RegionAwareStubEngagementBackend({("item", "GB"): (clicks, impressions)})
    recs = generate_recommendations(item_ids=["item"])
    ctr_prediction.CTRPredictionRanker(backend, ConstantPrior()).rank_items(recs, region="GB")
    assert recs[0].ranking_data.alpha == alpha
    assert recs[0].ranking_data.beta == beta


def test_time_sensitive_items_are_not_fresh():
    """Freshness only applies to eligible evergreen candidates."""
    recs = generate_recommendations(length=16, time_sensitive_count=16)
    ctr_prediction.CTRPredictionRanker(
        RegionAwareStubEngagementBackend({}), ConstantPrior()
    ).rank_items(recs, region="GB", rescaler=EngagementRescaler())
    assert not any(rec.ranking_data.is_fresh for rec in recs)


@pytest.mark.parametrize("hour", [0, 12, 23])
@pytest.mark.parametrize("counts", [None, (0, 0)])
def test_no_exposure_uses_hourly_fallback_for_items_and_sections(
    hour, counts, monkeypatch, mocker
):
    """Missing and explicit zero/zero rows use the same seasonal beta in both passes."""
    monkeypatch.setattr(ctr_prediction, "PSEUDOCOUNT_UTC_HOUR_OVERRIDE", hour)
    region = "GB-ctrpred_engb-treatment"
    metrics = {} if counts is None else {("item", region): counts}
    ranker = ctr_prediction.CTRPredictionRanker(
        RegionAwareStubEngagementBackend(metrics), ConstantPrior()
    )
    recs = generate_recommendations(item_ids=["item"])
    expected_alpha, expected_beta = ctr_prediction._missing_sparse_row_pseudocounts(region)
    ranker.rank_items(recs, region="GB", engagement_region=region)
    assert recs[0].ranking_data.alpha == pytest.approx(expected_alpha)
    assert recs[0].ranking_data.beta == pytest.approx(expected_beta)
    sections = generate_sections_feed(section_count=1)
    sections["top_stories_section"].recommendations = recs
    sample = mocker.patch.object(ctr_prediction.beta, "rvs", return_value=0.5)
    ranker.rank_sections(sections, region="GB", engagement_region=region)
    sample.assert_called_once_with(expected_alpha, expected_beta)
