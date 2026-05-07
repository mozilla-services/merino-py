"""Ranker that scores items via the LinTS interest backend.

Parallels ``ContextualRanker`` in shape, but the per-item score comes from a
single posterior draw of the LinTS-interest model (``θ̃ = θ̂ + v · L^{-T} ε``)
rather than a precomputed slate. Items the model doesn't know fall back to
Thompson sampling on the engagement Beta posterior, matching the cohort
ranker's "no ML score" branch.
"""

import logging

import numpy as np
from scipy.stats import beta

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.ml_backends.lints_interest_model import (
    EmptyLinTSInterestBackend,
    LinTSInterestBackend,
)
from merino.curated_recommendations.prior_backends.protocol import (
    EngagementRescaler,
    PriorBackend,
)
from merino.curated_recommendations.protocol import (
    CuratedRecommendation,
    ProcessedInterests,
    RankingData,
    Section,
)
from merino.curated_recommendations.rankers.ranker import Ranker
from merino.curated_recommendations.rankers.utils import (
    REGION_ENGAGEMENT_WEIGHT,
    filter_fresh_items_with_probability,
    renumber_sections,
)

logger = logging.getLogger(__name__)


class InterestRanker(Ranker):
    """Ranker backed by the LinTS-interest model.

    For each request:
      1. Sample θ̃ once from the model's posterior via the packed-triangular
         solve (handled inside ``backend.score_request``).
      2. Score every candidate the model knows about.
      3. For candidates the model doesn't know (e.g. items added since the
         last training cycle), fall back to vanilla Thompson sampling on the
         engagement Beta posterior — same fallback as ``ContextualRanker``.

    ``personal_interests.scores`` from ``decode_dp_interests`` already
    produces topic-name-keyed strength floats (and a string model id key
    that the backend ignores), so we pass it through directly.
    """

    def __init__(
        self,
        engagement_backend: EngagementBackend,
        prior_backend: PriorBackend,
        surface_id: SurfaceId,
        lints_backend: LinTSInterestBackend | EmptyLinTSInterestBackend,
        region_weight: float = REGION_ENGAGEMENT_WEIGHT,
    ) -> None:
        super().__init__(engagement_backend, prior_backend, region_weight)
        self.surface_id: SurfaceId = surface_id
        self.lints_backend = lints_backend

    def rank_items(
        self,
        recs: list[CuratedRecommendation],
        rescaler: EngagementRescaler | None = None,
        personal_interests: ProcessedInterests | None = None,
        region: str | None = None,
    ) -> list[CuratedRecommendation]:
        """Score and sort recommendations using the LinTS-interest model.

        Falls back to vanilla Thompson sampling for items the model doesn't
        know, and for the whole list if ``personal_interests`` is missing.
        """
        rng = np.random.default_rng()
        fresh_items_limit_prior_threshold_multiplier: float = (
            rescaler.fresh_items_limit_prior_threshold_multiplier if rescaler else 0
        )

        # Without strengths there's nothing to personalize against; scoring
        # would degenerate to bias-only for everyone. Fall through cleanly.
        strengths_dict: dict[str, float] = {}
        if personal_interests is not None:
            for k, v in personal_interests.scores.items():
                if isinstance(v, (int, float)):
                    strengths_dict[k] = float(v)

        # Single posterior draw → score the entire candidate list at once.
        # Items not known to the model still get a bias + topic_main score
        # from the backend, but we override that below with vanilla TS so
        # truly-fresh items get the wider-posterior exploration that bias-
        # only scoring can't provide.
        candidate_ids = [rec.corpusItemId for rec in recs]
        try:
            model_scores = self.lints_backend.score_request(
                self.surface_id, strengths_dict, candidate_ids, rng
            )
        except Exception as e:
            logger.error(f"InterestRanker: score_request failed; falling back: {e}")
            model_scores = None

        for r, rec in enumerate(recs):
            opens, no_opens, a_prior, b_prior, non_rescaled_b_prior = self.compute_interactions(
                rec, rescaler, region
            )

            # Decide between LinTS score (item known to the model) and
            # vanilla TS Beta sample (unknown item, or scoring failed
            # entirely). Mirrors ContextualRanker's "no ML score → Beta"
            # fallback, but the discriminator is item membership in the
            # LinTS index rather than presence in a slate.
            score: float
            if model_scores is not None and self.lints_backend.has_item(
                self.surface_id, rec.corpusItemId
            ):
                score = float(model_scores[r])
            else:
                alpha_val = opens + max(a_prior, 1e-18)
                beta_val = no_opens + max(b_prior, 1e-18)
                score = float(beta.rvs(alpha_val, beta_val))

            is_fresh = False
            remaining_fresh_impressions = 0
            beta_value_for_fresh_check = non_rescaled_b_prior
            if fresh_items_limit_prior_threshold_multiplier > 0 and not rec.isTimeSensitive:
                target_no_opens = (
                    beta_value_for_fresh_check * fresh_items_limit_prior_threshold_multiplier
                )
                if no_opens < target_no_opens:
                    is_fresh = True
                    remaining_fresh_impressions = int(target_no_opens - no_opens)

            rec.ranking_data = RankingData(
                score=score,
                alpha=0,
                beta=0,
                is_fresh=is_fresh,
                remaining_impressions=remaining_fresh_impressions,
            )

        return sorted(
            recs,
            key=lambda r: r.ranking_data.score if r.ranking_data is not None else float("-inf"),
            reverse=True,
        )

    def rank_sections(
        self,
        sections: dict[str, Section],
        top_n: int = 4,
        rescaler: EngagementRescaler | None = None,
    ) -> dict[str, Section]:
        """Rank sections by mean score of their top items.

        Same algorithm ``ContextualRanker.rank_sections`` uses; reproduced
        here so the LinTS path doesn't have to hold a reference to the
        cohort ranker's instance.
        """

        def sample_score(sec: Section) -> float:
            fresh_retain_likelyhood = (
                rescaler.fresh_items_section_ranking_max_percentage
                if rescaler is not None
                else 0.0
            )
            top_recs, _ = filter_fresh_items_with_probability(
                sec.recommendations, fresh_story_prob=fresh_retain_likelyhood, max_items=top_n
            )
            total_score = 0.0
            n_scores = 0
            for rec in top_recs:
                if rec.ranking_data:
                    total_score += rec.ranking_data.score
                    n_scores += 1
            return total_score / n_scores if n_scores > 0 else 0.0

        ordered = sorted(sections.items(), key=lambda kv: sample_score(kv[1]), reverse=True)
        return renumber_sections(ordered)
