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
    if enrolled:
        items = treatment_items if treatment else vanilla_items
        sections = treatment_sections if treatment else vanilla_sections
        assert items.call_args.kwargs["engagement_region"] == engagement_region
        assert sections.call_args.kwargs["engagement_region"] == engagement_region


@pytest.mark.parametrize("hour", [0, 12, 23])
def test_missing_branch_rows_fall_back_to_country_counts(hour, monkeypatch):
    """An entirely missing branch uses country counts without global blending."""
    monkeypatch.setattr(ctr_prediction, "PSEUDOCOUNT_UTC_HOUR_OVERRIDE", hour)
    backend = RegionAwareStubEngagementBackend({("item", "GB"): (900, 1000)})
    ranker = ctr_prediction.CTRPredictionRanker(backend, ConstantPrior())
    recs = generate_recommendations(item_ids=["item"])
    ranker.rank_items(recs, region="GB", engagement_region="GB-ctrpred_engb-treatment")
    data = recs[0].ranking_data
    assert data.alpha == 900
    assert data.beta == 100
    assert ("item", "GB") in backend.calls


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


@pytest.mark.parametrize("clicks,impressions,alpha,beta", [(0, 10, 1e-18, 10), (5, 10, 5, 5)])
def test_existing_valid_rows(clicks, impressions, alpha, beta):
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
@pytest.mark.parametrize("counts", [None, (0, 0), (5, 3), (5, 5), (5, 0), (-1, 10), (0, -1)])
def test_missing_or_invalid_rows_use_hourly_fallback_for_items_and_sections(
    hour, counts, monkeypatch, mocker
):
    """Unusable rows get a seasonal posterior, never a near-certain CTR of one."""
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


@pytest.mark.parametrize("counts", [None, (0, 0), (0, 100), (5, 5), (5, 100)])
@pytest.mark.parametrize("branch_prior", [False, True])
def test_control_uses_only_branch_engagement_and_priors(counts, branch_prior, mocker):
    """Control uses country counts only when the entire branch is missing, without blending."""
    from merino.curated_recommendations.prior_backends.protocol import Prior
    from tests.unit.curated_recommendations.test_rankers import RegionAwareStubPriorBackend

    region = "GB-ctrpred_engb-control"
    metrics = {("item", None): (500, 1000), ("item", "GB"): (800, 1000)}
    if counts is not None:
        metrics[("item", region)] = counts
    engagement = RegionAwareStubEngagementBackend(metrics)
    cohort_prior = Prior(alpha=2, beta=20, total_impressions_per_day=1000)
    priors = RegionAwareStubPriorBackend(
        {
            None: cohort_prior,
            "GB": cohort_prior,
            **({region: cohort_prior} if branch_prior else {}),
        }
    )
    ranker = ThompsonSamplingRanker(engagement, priors, region_weight=1.0)
    recs = generate_recommendations(item_ids=["item"])
    ranker.rank_items(recs, region="GB", engagement_region=region)
    clicks, impressions = counts if counts is not None else (800, 1000)
    prior = cohort_prior if branch_prior else ConstantPrior().get()
    assert recs[0].ranking_data.alpha == clicks + prior.alpha
    assert recs[0].ranking_data.beta == impressions - clicks + prior.beta

    sections = generate_sections_feed(section_count=1)
    sections["top_stories_section"].recommendations = recs
    sample = mocker.patch(
        "merino.curated_recommendations.rankers.t_sampling.beta.rvs", return_value=0.5
    )
    ranker.rank_sections(sections, region="GB", engagement_region=region)
    # Retain vanilla section aggregation and its fixed prior.
    fixed = ConstantPrior().get()
    sample.assert_called_once_with(
        max(clicks + fixed.alpha, 1.0), max(impressions - 2 * clicks + fixed.beta, 1.0)
    )
    assert all(lookup_region in {region, "GB"} for _, lookup_region in engagement.calls)
    if counts is not None:
        assert all(lookup_region == region for _, lookup_region in engagement.calls)
    assert all(lookup_region == region for lookup_region in priors.calls)


@pytest.mark.parametrize("branch", ["control", "treatment"])
@pytest.mark.parametrize("has_branch_row", [False, True])
def test_whole_pass_fallback_never_blends_global(branch, has_branch_row, mocker):
    """Item and section passes select one region, including for partially populated branches."""
    region = f"GB-ctrpred_engb-{branch}"
    metrics = {
        (item, lookup): counts
        for item in ("a", "b")
        for lookup, counts in [(None, (999, 1000)), ("GB", (3, 30))]
    }
    if has_branch_row:
        metrics[("a", region)] = (2, 20)
    backend = RegionAwareStubEngagementBackend(metrics)
    if branch == "control":
        ranker = ThompsonSamplingRanker(backend, ConstantPrior(), region_weight=1.0)
    else:
        ranker = ctr_prediction.CTRPredictionRanker(backend, ConstantPrior())
    recs = generate_recommendations(item_ids=["a", "b"])
    ranker.rank_items(recs, region="GB", engagement_region=region)
    if not has_branch_row:
        prior = ConstantPrior().get()
        for rec in recs:
            assert rec.ranking_data.alpha == (3 + prior.alpha if branch == "control" else 3)
            assert rec.ranking_data.beta == (27 + prior.beta if branch == "control" else 27)
    assert not any(lookup is None for _, lookup in backend.calls)
    assert any(lookup == "GB" for _, lookup in backend.calls) == (not has_branch_row)
    backend.calls.clear()
    sections = generate_sections_feed(section_count=1)
    sections["top_stories_section"].recommendations = recs
    sample = mocker.patch.object(ctr_prediction.beta, "rvs", return_value=0.5)
    ranker.rank_sections(sections, region="GB", engagement_region=region)
    if not has_branch_row and branch == "treatment":
        sample.assert_called_once_with(6.0, 54.0)
    assert not any(lookup is None for _, lookup in backend.calls)
    assert any(lookup == "GB" for _, lookup in backend.calls) == (not has_branch_row)
