"""CTR prediction treatment ranking using seasonal pseudo-counts and fractional freshness."""

from datetime import datetime, timezone
from math import ceil
from typing import TypedDict

from merino.curated_recommendations.engagement_backends.protocol import Engagement
from merino.curated_recommendations.rankers.t_sampling import PERSONALIZATION_TOPIC_WEIGHTING
from merino.curated_recommendations.ml_backends.static_local_model import DEFAULT_INTERESTS_KEY
from merino.curated_recommendations.prior_backends.protocol import (
    EngagementRescaler,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    Section,
    ProcessedInterests,
    RankingData,
)
from scipy.stats import beta

from merino.curated_recommendations.rankers.ranker import Ranker
from merino.curated_recommendations.rankers.utils import (
    INFERRED_SCORE_WEIGHT,
    filter_fresh_items_with_probability,
    renumber_sections,
)

BETA_EPSILON = 1e-18
PSEUDOCOUNT_MIN_STRENGTH = 1.0
PSEUDOCOUNT_MAX_STRENGTH = 10_000_000.0
# BQETL applies 32x strength to all emitted pseudo-count rows. Consume those rows
# as-is; apply this multiplier only when synthesizing the sparse-row fallback.
# It preserves the hourly mean but reduces Beta variance by approximately 32x
# before clipping. Fallback concentration can be evaluated separately in simulation.
PSEUDOCOUNT_STRENGTH_MULTIPLIER = 32.0
PSEUDO_FRESH_CANDIDATE_FRACTION = 0.125
PSEUDOCOUNT_UTC_HOUR_OVERRIDE: int | None = None


# Full-dataset ACTRSSM constants fitted on the en_GB 2026-08-12 to 2026-08-19
# replay dataset. These constants define the ctrpred_engb treatment fallback.
class SeasonalConstants(TypedDict):
    """Fitted hourly CTR and latent-state variance parameters."""

    global_ctr: float
    hourly_ctr: list[float]
    phi: float
    process_variance: float
    initial_variance: float


ACTRSSM_CONSTANTS_BY_REGION: dict[str | None, SeasonalConstants] = {
    None: {
        "global_ctr": 0.004671416593011661,
        "hourly_ctr": [
            0.0036027502814320717,
            0.003369765113772096,
            0.00336274066790737,
            0.003219103012237948,
            0.003159189818237718,
            0.003671162603241415,
            0.004770885536815382,
            0.005640864258731302,
            0.00608163077842357,
            0.005800540394055925,
            0.005662234119213514,
            0.00551304174144006,
            0.0051427439967683545,
            0.004960715682975525,
            0.004972184218202783,
            0.004862709894616185,
            0.004701100796243366,
            0.004502729318303354,
            0.004508624902652288,
            0.004646551786458396,
            0.004308206323994455,
            0.004222887903659873,
            0.004161383105015371,
            0.0039168636336211204,
        ],
        "phi": 0.8035290571092072,
        "process_variance": 0.05702594902328452,
        "initial_variance": 1.0601384284808002,
    },
    "GB": {
        "global_ctr": 0.00549142617968888,
        "hourly_ctr": [
            0.0037897577120721564,
            0.0035874066829025995,
            0.0036730439822962816,
            0.004293027405310703,
            0.005289842319061653,
            0.006487817232205769,
            0.006947288889418829,
            0.00678856494788479,
            0.006775118639931629,
            0.006349082720865816,
            0.006132815554137066,
            0.006021984817201792,
            0.005620085412221571,
            0.005481977400190812,
            0.005543267234804683,
            0.005578956877204055,
            0.005454693303285034,
            0.0048683316001689935,
            0.004597954489191772,
            0.004499000427179724,
            0.004454265152352611,
            0.004432251843976086,
            0.004281685879836372,
            0.004073081680422711,
        ],
        "phi": 0.7786195907676119,
        "process_variance": 0.07397743278083943,
        "initial_variance": 0.9194228740523188,
    },
}


def _pseudocount_utc_hour() -> int:
    """Return the UTC hour used for missing-row seasonal pseudo-counts."""
    if PSEUDOCOUNT_UTC_HOUR_OVERRIDE is not None:
        return PSEUDOCOUNT_UTC_HOUR_OVERRIDE
    return datetime.now(tz=timezone.utc).hour


def _constants_for_region(region: str | None) -> SeasonalConstants:
    """Return fitted ACTRSSM constants for a Merino engagement region."""
    if region is None:
        return ACTRSSM_CONSTANTS_BY_REGION[None]
    country = str(region).split("-", 1)[0].upper()
    return ACTRSSM_CONSTANTS_BY_REGION.get(country, ACTRSSM_CONSTANTS_BY_REGION[None])


def _fallback_logit_variance(region: str | None) -> float:
    """Return the model's stationary no-observation logit variance."""
    constants = _constants_for_region(region)
    return constants["process_variance"] / (1.0 - constants["phi"] ** 2)


def _engagement_logit_variance(engagement: Engagement | None, region: str | None) -> float:
    """Reconstruct model uncertainty before serving rescaling or Beta epsilon clamps."""
    if engagement is None:
        return _fallback_logit_variance(region)
    opens = float(engagement.click_count)
    no_opens = float(engagement.impression_count) - opens
    strength = opens + no_opens
    if opens == 0 and strength >= PSEUDOCOUNT_MAX_STRENGTH:
        # The production zero-click boundary at maximum strength is well-observed,
        # not infinitely uncertain. Exact pre-clipping variance is unrecoverable.
        return 0.0
    if opens <= 0 or no_opens <= 0:
        return _fallback_logit_variance(region)
    multiplier = PSEUDOCOUNT_STRENGTH_MULTIPLIER
    # Invert K = s * (1 / (p * (1-p) * V) - 1). At the upper strength cap,
    # this is a conservative upper bound, not the exact pre-clipping variance.
    return multiplier * strength * strength / (opens * no_opens * (strength + multiplier))


def _missing_sparse_row_pseudocounts(region: str | None) -> tuple[float, float]:
    """Return fallback pseudo-clicks/non-clicks for an absent artifact row.

    Sparse pseudo-count artifacts omit low-history candidates. Treat those
    missing rows as zero observed exposure, not as an old additive Merino prior.
    Merino has no per-item row state here, so use the fitted seasonal mean at the
    current UTC hour. Derive an initial Beta concentration from the steady-state
    no-observation logit variance using a local variance approximation, then apply
    the serving strength multiplier and bounds. The returned pseudo-counts retain
    the hourly mean but do not preserve that variance: the 32x multiplier reduces
    Beta variance by approximately 32x when neither strength bound is active.
    These synthetic counts represent concentration, not observed exposure.
    """
    constants = _constants_for_region(region)
    hour = _pseudocount_utc_hour()
    probability = float(constants["hourly_ctr"][hour])
    stationary_variance = _fallback_logit_variance(region)

    raw_strength = 1.0 / (probability * (1.0 - probability) * stationary_variance) - 1.0
    matched_strength = min(
        max(raw_strength, PSEUDOCOUNT_MIN_STRENGTH),
        PSEUDOCOUNT_MAX_STRENGTH,
    )
    strength = min(
        max(matched_strength * PSEUDOCOUNT_STRENGTH_MULTIPLIER, PSEUDOCOUNT_MIN_STRENGTH),
        PSEUDOCOUNT_MAX_STRENGTH,
    )
    return probability * strength, (1.0 - probability) * strength


def _opens_no_opens_from_engagement(
    engagement: Engagement | None, region: str | None
) -> tuple[float, float]:
    """Use seasonal pseudo-counts when a row cannot supply a valid posterior."""
    if (
        engagement is None
        or engagement.click_count < 0
        or engagement.impression_count <= engagement.click_count
    ):
        # Zero/zero and inconsistent rows have no usable non-click count. An epsilon
        # beta would give positive-click rows a near-certain CTR of 1, dominating ranks.
        return _missing_sparse_row_pseudocounts(region)
    return float(engagement.click_count), float(
        engagement.impression_count - engagement.click_count
    )


class CTRPredictionRanker(Ranker):
    """Rank items and sections from CTR prediction pseudo-count artifacts."""

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Rank items by sampling Beta distributions from rescaled pseudo-counts.

        Use the selected region's counts directly as Beta parameters, without an
        additive Merino prior or global blending. Missing, zero/zero, and invalid
        rows use seasonal hourly pseudo-counts. Apply interest boosts, mark the
        highest reconstructed logit-variance fraction fresh (rounded up), and
        suppress excess fresh items. Uncertainty uses counts before serving rescaling;
        missing and unusable counts receive the model's cold-start variance.

        Args:
            recs: Candidates to score before publisher spreading.
            rescaler: Optional count rescaling and freshness-throttle settings.
            personal_interests: Optional normalized interests for score boosts.
            region: Base country key used if no candidate has branch engagement.
            engagement_region: Engagement lookup key, typically the treatment branch.
                Defaults to region; falls back to region for the whole candidate list
                if none has a row under this key.

        Returns:
            Candidates sorted by descending score, with ranking_data updated in place.
        """
        engagement_region = self.resolve_engagement_region(
            recs, region, engagement_region if engagement_region is not None else region
        )
        fresh_items_max: int = rescaler.fresh_items_max if rescaler else 0

        def boost_interest(rec: CuratedRecommendation) -> float:
            if personal_interests is None or rec.topic is None:
                return 0.0
            if rec.topic.value not in personal_interests.normalized_scores:
                return (
                    personal_interests.normalized_scores.get(DEFAULT_INTERESTS_KEY, 0.0)
                    * INFERRED_SCORE_WEIGHT
                )
            return (
                personal_interests.normalized_scores[rec.topic.value]
                * INFERRED_SCORE_WEIGHT
                * PERSONALIZATION_TOPIC_WEIGHTING.get(rec.topic, 1.0)
            )

        logit_variance_by_rec: dict[int, float] = {}

        def pseudo_count_interactions(rec: CuratedRecommendation) -> tuple[float, float]:
            """Return pseudo-clicks/non-clicks without adding Merino priors.

            Valid artifact rows are already ACTRSSM pseudo-counts. Missing,
            zero/zero, or inconsistent rows use the seasonal cold-start
            pseudo-counts for the active engagement region.
            """
            engagement = self.engagement_backend.get(rec.corpusItemId, engagement_region)
            logit_variance_by_rec[id(rec)] = _engagement_logit_variance(
                engagement, engagement_region
            )
            opens, no_opens = _opens_no_opens_from_engagement(engagement, engagement_region)
            if rescaler is not None:
                opens, no_opens = rescaler.rescale(rec, opens, no_opens)
            return opens, no_opens

        def compute_ranking_scores(rec: CuratedRecommendation) -> None:
            """Sample from pseudo-counts for a recommendation."""
            opens, no_opens = pseudo_count_interactions(rec)
            # Under the production pseudo-count contract, zero pseudo-clicks occur
            # only after 10M impressions with no clicks. Keep epsilon clamping here.
            alpha_val = max(opens, BETA_EPSILON)
            beta_val = max(no_opens, BETA_EPSILON)
            rec.ranking_data = RankingData(
                score=float(beta.rvs(alpha_val, beta_val)) + boost_interest(rec),
                alpha=alpha_val,
                beta=beta_val,
            )

        def mark_fresh_items() -> None:
            """Use the existing freshness throttle for the highest model uncertainty."""
            if rescaler is None or PSEUDO_FRESH_CANDIDATE_FRACTION <= 0:
                return
            eligible = [
                rec for rec in recs if rec.ranking_data is not None and not rec.isTimeSensitive
            ]
            uncertain_count = ceil(len(eligible) * PSEUDO_FRESH_CANDIDATE_FRACTION)
            most_uncertain_first = sorted(
                eligible, key=lambda rec: logit_variance_by_rec[id(rec)], reverse=True
            )
            for rec in most_uncertain_first[:uncertain_count]:
                if rec.ranking_data is not None:
                    # is_fresh is the existing downstream throttle flag. Here it denotes
                    # high logit uncertainty, not age or a pseudo-impression threshold.
                    rec.ranking_data.is_fresh = True
                    rec.ranking_data.remaining_impressions = 0

        for rec in recs:
            compute_ranking_scores(rec)
        mark_fresh_items()
        self.suppress_fresh_items(recs, fresh_items_max)
        # Sort the recommendations from best to worst sampled score & renumber
        sorted_recs = sorted(
            recs,
            key=lambda r: r.ranking_data.score if r.ranking_data is not None else float("-inf"),
            reverse=True,
        )
        return sorted_recs

    def rank_sections(
        self,
        sections: dict[str, Section],
        top_n: int = 4,
        rescaler: EngagementRescaler | None = None,
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> dict[str, Section]:
        """Rank sections by sampling Beta distributions from summed item pseudo-counts.

        Select up to top_n items per section using the freshness filter, rescale
        their pseudo-counts, and sum them into section Beta parameters. Missing,
        zero/zero, and invalid rows use seasonal hourly pseudo-counts. No additive
        Merino prior or global engagement blend is applied; section boosts are
        added after sampling.

        Args:
            sections: Section IDs mapped to sections containing ranked recommendations.
            top_n: Maximum number of retained items contributing to each section score.
            rescaler: Optional count rescaling, fresh-item retention, and section boosts.
            region: Base country key used if no candidate has branch engagement.
            engagement_region: Engagement lookup key, typically the treatment branch.
                Defaults to region; falls back to region for all sections if none of
                their candidates has a row under this key.

        Returns:
            Sections ordered by sampled score with updated receivedFeedRank values.
        """
        engagement_region = self.resolve_engagement_region(
            [rec for sec in sections.values() for rec in sec.recommendations],
            region,
            engagement_region if engagement_region is not None else region,
        )

        def sample_score(section_id: str, sec: Section) -> float:
            """Sample from the summed pseudo-counts of retained top items."""
            fresh_retain_likelyhood = (
                rescaler.fresh_items_section_ranking_max_percentage
                if rescaler is not None
                else 0.0
            )
            recs, _ = filter_fresh_items_with_probability(
                sec.recommendations, fresh_story_prob=fresh_retain_likelyhood, max_items=top_n
            )

            total_opens = 0.0
            total_no_opens = 0.0

            for rec in recs:
                engagement = self.engagement_backend.get(rec.corpusItemId, engagement_region)
                opens, no_opens = _opens_no_opens_from_engagement(engagement, engagement_region)
                if rescaler is not None:
                    opens, no_opens = rescaler.rescale(rec, opens, no_opens)

                total_opens += opens
                total_no_opens += no_opens

            # Section ranking samples the Beta implied by summed item pseudo-counts.
            opens = max(total_opens, BETA_EPSILON)
            no_opens = max(total_no_opens, BETA_EPSILON)

            boost_amount = rescaler.boost_section(section_id) if rescaler is not None else 0.0

            return float(beta.rvs(opens, no_opens)) + boost_amount

        # sort sections by sampled score, highest first
        ordered = sorted(sections.items(), key=lambda kv: sample_score(kv[0], kv[1]), reverse=True)
        return renumber_sections(ordered)
