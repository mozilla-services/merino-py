"""Unit tests for the LinTS InterestRanker.

These tests stub the LinTS backend so we can drive deterministic scenarios
without building real safetensors. Backend correctness is covered separately
in ``tests/unit/curated_recommendations/ml_backends/test_lints_interest_model.py``.

Coverage:
  - ``rank_items`` uses the model's score for items the model knows
  - Falls back to vanilla TS Beta sampling for items the model doesn't know
  - Falls back cleanly when ``score_request`` itself raises
  - Sorts strictly by descending score
  - Filters non-numeric ``personal_interests.scores`` entries before passing
    them to the backend
  - ``rank_sections`` orders by mean of top-K item scores
"""

from __future__ import annotations

import numpy as np
import pytest

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)
from merino.curated_recommendations.prior_backends.protocol import (
    EngagementRescaler,
    Prior,
    PriorBackend,
)
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import (
    ProcessedInterests,
    RankingData,
    Section,
)
from merino.curated_recommendations.rankers.interest_ranker import InterestRanker
from tests.unit.curated_recommendations.fixtures import generate_recommendations


# -----------------------------------------------------------------------------
# Stubs / fakes
# -----------------------------------------------------------------------------
class StubPriorBackend(PriorBackend):
    """Returns a fixed Prior."""

    def __init__(self, prior: Prior | None = None):
        self._prior = prior or Prior(alpha=0.1, beta=99.9, average_ctr=0.001)

    def get(self, region: str | None = None) -> Prior:
        """Return the stubbed prior."""
        return self._prior

    @property
    def update_count(self) -> int:
        """Stub — never updates."""
        return 0


class StubEngagementBackend(EngagementBackend):
    """Returns Engagement records from a preconfigured dict, or None."""

    def __init__(self, metrics: dict[str, tuple[int, int]]) -> None:
        # corpusItemId → (clicks, impressions)
        self._metrics = metrics

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return the engagement, or None if no record."""
        if corpus_item_id not in self._metrics:
            return None
        clicks, impressions = self._metrics[corpus_item_id]
        return Engagement(
            corpus_item_id=corpus_item_id,
            region=region,
            click_count=clicks,
            impression_count=impressions,
            report_count=0,
        )

    @property
    def update_count(self) -> int:
        """Stub — never updates."""
        return 0


class FakeLinTSBackend:
    """Hand-rolled stand-in for ``LinTSInterestBackend`` with controllable scoring."""

    def __init__(
        self,
        valid: bool = True,
        known_items: set[str] | None = None,
        item_scores: dict[str, float] | None = None,
        raise_on_score: bool = False,
    ) -> None:
        self._valid = valid
        self._known = known_items or set()
        self._scores = item_scores or {}
        self._raise = raise_on_score
        self.last_strengths: dict[str, float] | None = None

    def is_valid(self, surface_id: SurfaceId) -> bool:
        """Return whichever flag the test set."""
        return self._valid

    def has_item(self, surface_id: SurfaceId, corpus_item_id: str) -> bool:
        """Return True iff the test added the item to the known set."""
        return corpus_item_id in self._known

    def score_request(
        self,
        surface_id: SurfaceId,
        strengths: dict[str, float],
        candidate_item_ids: list[str],
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Return preconfigured scores; record strengths for assertion."""
        if self._raise:
            raise RuntimeError("simulated stpsv failure")
        # Capture what InterestRanker passed us so tests can assert filtering.
        self.last_strengths = dict(strengths)
        return np.array(
            [self._scores.get(iid, 0.0) for iid in candidate_item_ids],
            dtype=np.float32,
        )


def _make_ranker(
    backend: FakeLinTSBackend,
    engagement_metrics: dict[str, tuple[int, int]] | None = None,
) -> InterestRanker:
    """Build an InterestRanker with stubbed engagement / prior backends."""
    return InterestRanker(
        engagement_backend=StubEngagementBackend(engagement_metrics or {}),
        prior_backend=StubPriorBackend(),
        surface_id=SurfaceId.NEW_TAB_EN_US,
        lints_backend=backend,  # type: ignore[arg-type]
    )


# -----------------------------------------------------------------------------
# rank_items — known items get the model's score, unknowns fall back to Beta.
# -----------------------------------------------------------------------------
def test_known_items_get_model_score() -> None:
    """Items in the model's index receive its sampled score; sorting follows."""
    recs = generate_recommendations(item_ids=["A", "B", "C"], time_sensitive_count=0)
    backend = FakeLinTSBackend(
        known_items={"A", "B", "C"},
        item_scores={"A": 0.10, "B": 0.30, "C": 0.05},
    )
    ranker = _make_ranker(backend)
    personal = ProcessedInterests(
        scores={"sports": 0.5, "tech": 0.46}, normalized_scores={}, cohort=None
    )

    ranked = ranker.rank_items(recs, personal_interests=personal)
    # Highest-scoring first.
    assert [r.corpusItemId for r in ranked] == ["B", "A", "C"]
    for r in ranked:
        assert r.ranking_data is not None
    # The score on each rec equals what the backend returned.
    score_by_id = {
        r.corpusItemId: r.ranking_data.score for r in ranked if r.ranking_data is not None
    }
    assert score_by_id["B"] == pytest.approx(0.30, rel=1e-6)
    assert score_by_id["A"] == pytest.approx(0.10, rel=1e-6)
    assert score_by_id["C"] == pytest.approx(0.05, rel=1e-6)


def test_strengths_passed_through_unchanged() -> None:
    """Floats from ``personal_interests.scores`` reach the backend with
    the same values — no scaling, no reordering.

    ``ProcessedInterests.scores`` is ``dict[str, float]`` so pydantic already
    prevents string-valued entries from existing in the public contract. The
    ranker still has a defensive ``isinstance`` filter as belt-and-suspenders
    against any future contract drift.
    """
    recs = generate_recommendations(item_ids=["A"], time_sensitive_count=0)
    backend = FakeLinTSBackend(known_items={"A"}, item_scores={"A": 0.5})
    ranker = _make_ranker(backend)
    personal = ProcessedInterests(
        scores={"sports": 0.46, "tech": 0.0, "science": 0.8},
        normalized_scores={},
        cohort=None,
    )
    ranker.rank_items(recs, personal_interests=personal)

    assert backend.last_strengths is not None
    assert backend.last_strengths == {"sports": 0.46, "tech": 0.0, "science": 0.8}


def test_unknown_items_use_vanilla_beta_fallback() -> None:
    """Items not in the model's index get a Beta(opens+a, no_opens+b) sample,
    not a model score. Verify by loading items into the engagement backend
    with very different click/impression ratios so their expected ranks are
    predictable.
    """
    recs = generate_recommendations(item_ids=["high_ctr", "low_ctr"], time_sensitive_count=0)
    backend = FakeLinTSBackend(known_items=set(), item_scores={})  # nothing known
    ranker = _make_ranker(
        backend,
        engagement_metrics={
            "high_ctr": (90, 100),  # 90% empirical CTR
            "low_ctr": (1, 100),  # 1% empirical CTR
        },
    )
    # Average across enough Beta draws to wash out variance.
    wins = 0
    n = 200
    for _ in range(n):
        ranked = ranker.rank_items(recs)
        if ranked[0].corpusItemId == "high_ctr":
            wins += 1
    # The Beta posterior for high_ctr (~0.9) dominates low_ctr (~0.01); 99%+
    # of draws should rank it first.
    assert wins >= 0.9 * n, f"high-CTR item ranked first only {wins}/{n} times"


def test_score_request_failure_falls_back_to_beta_for_all(caplog) -> None:
    """If the backend raises mid-request, every item — including 'known' ones —
    falls back to vanilla Beta sampling, and the failure is logged.
    """
    recs = generate_recommendations(
        item_ids=["known_high_ctr", "known_low_ctr"], time_sensitive_count=0
    )
    backend = FakeLinTSBackend(
        known_items={"known_high_ctr", "known_low_ctr"},
        raise_on_score=True,
    )
    ranker = _make_ranker(
        backend,
        engagement_metrics={
            "known_high_ctr": (90, 100),
            "known_low_ctr": (1, 100),
        },
    )
    ranked = ranker.rank_items(recs)
    # Sanity: ranker didn't crash
    assert len(ranked) == 2
    # Engagement-driven Beta should rank high_ctr first reliably here too.
    wins = 0
    n = 100
    for _ in range(n):
        ranked = ranker.rank_items(recs)
        if ranked[0].corpusItemId == "known_high_ctr":
            wins += 1
    assert wins >= 0.85 * n
    assert any("score_request failed" in r.message for r in caplog.records)


def test_personal_interests_none() -> None:
    """A None personal_interests still produces a ranked list (empty strengths)."""
    recs = generate_recommendations(item_ids=["A", "B"], time_sensitive_count=0)
    backend = FakeLinTSBackend(known_items={"A", "B"}, item_scores={"A": 0.2, "B": 0.7})
    ranker = _make_ranker(backend)

    ranked = ranker.rank_items(recs, personal_interests=None)
    assert [r.corpusItemId for r in ranked] == ["B", "A"]
    # Backend was still called — with an empty strength dict.
    assert backend.last_strengths == {}


def test_strict_score_descending_order() -> None:
    """Returned list is sorted strictly by descending score."""
    recs = generate_recommendations(item_ids=["a", "b", "c", "d", "e"], time_sensitive_count=0)
    backend = FakeLinTSBackend(
        known_items={"a", "b", "c", "d", "e"},
        item_scores={"a": 0.1, "b": 0.5, "c": 0.3, "d": 0.9, "e": 0.0},
    )
    ranker = _make_ranker(backend)

    ranked = ranker.rank_items(recs)
    scores = [r.ranking_data.score for r in ranked if r.ranking_data]
    assert scores == sorted(scores, reverse=True)


def test_low_impression_items_marked_fresh_with_active_rescaler() -> None:
    """A rescaler with ``fresh_items_limit_prior_threshold_multiplier > 0``
    should flag items whose ``no_opens`` is below the derived target.
    Verifies the freshness branch in rank_items actually fires.
    """
    recs = generate_recommendations(item_ids=["fresh_item", "stale_item"], time_sensitive_count=0)
    backend = FakeLinTSBackend(
        known_items={"fresh_item", "stale_item"},
        item_scores={"fresh_item": 0.5, "stale_item": 0.5},
    )
    # Rescaler with the threshold multiplier set; the base Ranker's
    # ``compute_interactions`` returns priors via the stub, and the
    # ratio (no_opens vs target_no_opens) decides freshness.
    rescaler = EngagementRescaler(fresh_items_limit_prior_threshold_multiplier=10.0)
    ranker = _make_ranker(
        backend,
        engagement_metrics={
            # fresh_item has very few no_opens (well below the target) → is_fresh=True
            "fresh_item": (1, 5),
            # stale_item has many no_opens → not fresh
            "stale_item": (1, 100_000),
        },
    )

    ranked = ranker.rank_items(recs, rescaler=rescaler)
    by_id = {r.corpusItemId: r for r in ranked}
    assert by_id["fresh_item"].ranking_data is not None
    assert by_id["fresh_item"].ranking_data.is_fresh is True
    assert by_id["fresh_item"].ranking_data.remaining_impressions > 0
    assert by_id["stale_item"].ranking_data is not None
    assert by_id["stale_item"].ranking_data.is_fresh is False


def test_non_numeric_strength_value_filtered() -> None:
    """Non-numeric scores entries (e.g. a string) get dropped before reaching the backend.

    Pydantic validation makes this branch hard to reach normally, but a
    misconfigured upstream or a future schema drift could put a non-numeric
    value in ``scores``. Using ``ProcessedInterests.model_construct`` here
    bypasses validation to exercise the defensive path.
    """
    recs = generate_recommendations(item_ids=["A"], time_sensitive_count=0)
    backend = FakeLinTSBackend(known_items={"A"}, item_scores={"A": 0.5})
    ranker = _make_ranker(backend)

    # Bypass pydantic validation so we can put a string in scores.
    bad_scores: dict[str, float] = {
        "sports": 0.46,
        "_metadata_string": "ignore_me",  # type: ignore[dict-item]
        "tech": 0.0,
    }
    personal = ProcessedInterests.model_construct(
        scores=bad_scores,
        normalized_scores={},
        cohort=None,
    )
    ranker.rank_items(recs, personal_interests=personal)

    assert backend.last_strengths is not None
    # String entry must NOT be passed to the backend
    assert "_metadata_string" not in backend.last_strengths
    # Numeric entries pass through unchanged
    assert backend.last_strengths["sports"] == pytest.approx(0.46)
    assert backend.last_strengths["tech"] == pytest.approx(0.0)


# -----------------------------------------------------------------------------
# rank_sections — sections ordered by mean score of their top-N items.
# -----------------------------------------------------------------------------
def _section_with_scores(scores: list[float]) -> Section:
    """Build a Section with `len(scores)` recommendations, each carrying the given score."""
    recs = generate_recommendations(
        item_ids=[f"id_{i}" for i in range(len(scores))], time_sensitive_count=0
    )
    for rec, s in zip(recs, scores):
        rec.ranking_data = RankingData(
            score=s, alpha=0, beta=0, is_fresh=False, remaining_impressions=0
        )
    sec = Section(
        receivedFeedRank=0,
        recommendations=recs,
        title="t",
        layout=layout_4_medium,
    )
    return sec


def test_rank_sections_orders_by_top_n_mean_score() -> None:
    """Sections sort by mean score of their top-N items, descending."""
    backend = FakeLinTSBackend()
    ranker = _make_ranker(backend)

    sections = {
        "low": _section_with_scores([0.1, 0.1, 0.1, 0.1]),
        "high": _section_with_scores([0.9, 0.8, 0.7, 0.6]),
        "mid": _section_with_scores([0.5, 0.4, 0.3, 0.2]),
    }
    ordered = ranker.rank_sections(sections, top_n=4)
    # Section ranks set by renumber_sections; we just want the ordering.
    # The first section in iteration order of the returned dict is the
    # highest-scoring one because dicts preserve insertion order.
    assert list(ordered.keys()) == ["high", "mid", "low"]


def test_rank_sections_sections_with_no_scored_recs_get_zero() -> None:
    """A section whose recs have no ranking_data falls to the bottom."""
    backend = FakeLinTSBackend()
    ranker = _make_ranker(backend)

    empty_section_recs = generate_recommendations(item_ids=["x", "y"], time_sensitive_count=0)
    # Don't set ranking_data on these recs.
    sections = {
        "empty": Section(
            receivedFeedRank=0,
            recommendations=empty_section_recs,
            title="t",
            layout=layout_4_medium,
        ),
        "scored": _section_with_scores([0.5, 0.5]),
    }
    ordered = ranker.rank_sections(sections, top_n=2)
    assert list(ordered.keys()) == ["scored", "empty"]
