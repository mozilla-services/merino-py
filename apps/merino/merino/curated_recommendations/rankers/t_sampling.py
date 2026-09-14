"""Algorithms for ranking curated recommendations."""

import logging
from datetime import datetime, timezone

from merino.curated_recommendations.corpus_backends.protocol import Topic
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

logger = logging.getLogger(__name__)

PERSONALIZATION_TOPIC_WEIGHTING = {
    Topic.ARTS: 0.6,
    Topic.POLITICS: 0.7,
    Topic.SPORTS: 0.8,
    Topic.TECHNOLOGY: 0.7,
}

BETA_EPSILON = 1e-18
PSEUDOCOUNT_MIN_STRENGTH = 1.0
PSEUDOCOUNT_MAX_STRENGTH = 10_000_000.0
PSEUDOCOUNT_STRENGTH_MULTIPLIER = 32.0
PSEUDO_FRESH_CANDIDATE_FRACTION = 0.125
PSEUDOCOUNT_UTC_HOUR_OVERRIDE: int | None = None

# Full-dataset ACTRSSM constants fitted on the en_GB 2026-08-12 to 2026-08-19
# replay dataset. This branch hardcodes the constants so the simulator can test
# sparse pseudo-count serving behavior before wiring config and GCS metadata.
ACTRSSM_CONSTANTS_BY_REGION = {
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


def _constants_for_region(region: str | None) -> dict[str, object]:
    """Return fitted ACTRSSM constants for a Merino engagement region."""
    if region is None:
        return ACTRSSM_CONSTANTS_BY_REGION[None]
    country = str(region).split("-", 1)[0].upper()
    return ACTRSSM_CONSTANTS_BY_REGION.get(country, ACTRSSM_CONSTANTS_BY_REGION[None])


def _missing_sparse_row_pseudocounts(region: str | None) -> tuple[float, float]:
    """Return fallback pseudo-clicks/non-clicks for an absent artifact row.

    Sparse pseudo-count artifacts omit low-history candidates. Treat those
    missing rows as zero observed exposure, not as an old additive Merino prior.
    Merino has no per-item row state here, so this uses the fitted seasonal
    fallback mean at the current UTC hour and the steady-state no-observation
    logit variance.
    """
    constants = _constants_for_region(region)
    hour = _pseudocount_utc_hour()
    probability = float(constants["hourly_ctr"][hour])
    phi = float(constants["phi"])
    process_variance = float(constants["process_variance"])
    stationary_variance = process_variance / (1.0 - phi**2)

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


def _opens_no_opens_from_engagement(engagement) -> tuple[float, float]:
    """Convert Merino engagement rows to Thompson alpha/beta observations."""
    opens = float(engagement.click_count)
    no_opens = float(engagement.impression_count) - opens
    return opens, max(no_opens, 0.0)


class ThompsonSamplingRanker(Ranker):
    """Base class for ranking curated recommendations"""

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        region: str | None = None,
        engagement_region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
        CTR with exploration of new items using a prior.

        :param recs: A list of recommendations in the desired order (pre-publisher spread).
        :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
        :param prior_backend: Provides prior alpha and beta values for Thompson sampling.
        :param region: Optionally, the client's region, e.g. 'US'.
        :param region_weight: In a weighted average, how much to weigh regional engagement.
        :param rescaler: Class that can up-scale interaction stats for certain items based on experiment size
        :param personal_interests User interests

        :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

        [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
        """
        engagement_region = self.resolve_engagement_region(recs, region, engagement_region)
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

        def pseudo_count_interactions(rec: CuratedRecommendation) -> tuple[float, float]:
            """Return pseudo-clicks/non-clicks without adding Merino priors.

            Existing artifact rows are already ACTRSSM pseudo-counts. Missing
            rows are sparse-artifact omissions, so synthesize the cold-start
            pseudo-counts for the active engagement region.
            """
            engagement = self.engagement_backend.get(rec.corpusItemId, engagement_region)
            if engagement is None:
                opens, no_opens = _missing_sparse_row_pseudocounts(engagement_region)
            else:
                opens, no_opens = _opens_no_opens_from_engagement(engagement)
            if rescaler is not None:
                opens, no_opens = rescaler.rescale(rec, opens, no_opens)
            return opens, no_opens

        def compute_ranking_scores(rec: CuratedRecommendation) -> float:
            """Sample from pseudo-counts for a recommendation."""
            opens, no_opens = pseudo_count_interactions(rec)
            alpha_val = max(opens, BETA_EPSILON)
            beta_val = max(no_opens, BETA_EPSILON)
            rec.ranking_data = RankingData(
                score=float(beta.rvs(alpha_val, beta_val)) + boost_interest(rec),
                alpha=alpha_val,
                beta=beta_val,
            )
            return no_opens

        def mark_lowest_pseudo_no_open_items_fresh(
            pseudo_no_opens_by_rec: dict[int, float],
        ) -> None:
            """Approximate Merino's fresh throttle after replacing priors.

            The normal freshness threshold is based on the old prior beta. This
            branch removes that prior, so use the fitted replay proxy: mark the
            lowest-pseudo-impression candidate fraction as fresh.
            """
            if rescaler is None or PSEUDO_FRESH_CANDIDATE_FRACTION <= 0:
                return
            eligible = [
                (pseudo_no_opens_by_rec[id(rec)], rec)
                for rec in recs
                if rec.ranking_data is not None and not rec.isTimeSensitive
            ]
            if not eligible:
                return
            fresh_count = round(len(eligible) * PSEUDO_FRESH_CANDIDATE_FRACTION)
            if fresh_count <= 0:
                return
            eligible.sort(key=lambda item: item[0])
            target_no_opens = eligible[min(fresh_count, len(eligible)) - 1][0]
            for no_opens, rec in eligible[:fresh_count]:
                if rec.ranking_data is not None:
                    rec.ranking_data.is_fresh = True
                    rec.ranking_data.remaining_impressions = int(
                        max(target_no_opens - no_opens, 0.0)
                    )

        pseudo_no_opens_by_rec = {}
        for rec in recs:
            pseudo_no_opens_by_rec[id(rec)] = compute_ranking_scores(rec)
        mark_lowest_pseudo_no_open_items_fresh(pseudo_no_opens_by_rec)
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
        """Re-rank sections using [Thompson sampling][thompson-sampling], based on the combined engagement of top items.

        :param sections: Mapping of section IDs to Section objects whose recommendations will be scored.
        :param engagement_backend: Provides aggregate click and impression engagement by corpusItemId.
        :param top_n: Number of top items in each section for which to sum engagement in the Thompson sampling score.
        :param rescaler: Class that can up-scale interaction stats for certain items based on experiment size

        :return: Mapping of section IDs to Section objects with updated receivedFeedRank.

        [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
        """
        engagement_region = self.resolve_engagement_region(
            [rec for sec in sections.values() for rec in sec.recommendations],
            region,
            engagement_region,
        )

        def sample_score(section_id: str, sec: Section) -> float:
            """Sample beta distribution for the combined engagement of the top _n_ items."""
            # sum clicks and impressions over top_n items

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
                if engagement is None:
                    opens, no_opens = _missing_sparse_row_pseudocounts(engagement_region)
                else:
                    opens, no_opens = _opens_no_opens_from_engagement(engagement)
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
