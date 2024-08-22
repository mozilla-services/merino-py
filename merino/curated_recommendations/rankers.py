"""Algorithms for ranking curated recommendations."""

from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.models import CuratedRecommendation
from scipy.stats import beta

DEFAULT_ALPHA_PRIOR = 188  # beta * P99 German NewTab CTR for 2023-03-28 to 2023-04-05 (1.5%)
DEFAULT_BETA_PRIOR = (
    12500  # 0.5% of median German NewTab item impressions for 2023-03-28 to 2023-04-05.
)


def thompson_sampling(
    recs: list[CuratedRecommendation],
    engagement_backend: EngagementBackend,
    alpha_prior=DEFAULT_ALPHA_PRIOR,
    beta_prior=DEFAULT_BETA_PRIOR,
) -> list[CuratedRecommendation]:
    """Re-rank items using [Thompson sampling][thompson-sampling], combining exploitation of known item
    CTR with exploration of new items using a prior.

    :param recs: A list of recommendations in the desired order (pre-publisher spread).
    :param engagement_backend: Provides aggregate click and impression engagement by scheduledCorpusItemId.
    :param alpha_prior: Prior successes (e.g., clicks). Must be > 0.
    :param beta_prior: Prior failures (e.g., non-click impressions). Must be > 0.

    :return: A re-ordered version of recs, ranked according to the Thompson sampling score.

    [thompson-sampling]: https://en.wikipedia.org/wiki/Thompson_sampling
    """

    def get_score(rec: CuratedRecommendation) -> float:
        opens = alpha_prior
        no_opens = beta_prior

        engagement = engagement_backend.get(rec.scheduledCorpusItemId)
        if engagement:
            opens += engagement.click_count
            no_opens += engagement.impression_count - engagement.click_count

        return float(beta.rvs(opens, no_opens))

    return sorted(recs, key=get_score, reverse=True)
