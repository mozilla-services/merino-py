"""Unit tests for merino/optimizers/thompson.py"""

import pytest

from merino.optimizers.models import EngagementMetrics, ThompsonCandidate, ThompsonConfig
from merino.optimizers.thompson import ThompsonSampler


def make_candidate(candidate_id: str, engaged: int, attempted: int) -> ThompsonCandidate:
    """Build a ThompsonCandidate."""
    return ThompsonCandidate(
        id=candidate_id, metrics=EngagementMetrics(engaged=engaged, attempted=attempted)
    )


class TestThompsonSamplerEmptyInput:
    """Tests for edge cases with no candidates."""

    def test_empty_candidates_returns_none(self) -> None:
        """sample() with no candidates returns None."""
        sampler = ThompsonSampler(config=ThompsonConfig())
        assert sampler.sample([]) is None


class TestThompsonSamplerSingleCandidate:
    """Tests with a single candidate."""

    def test_single_candidate_no_dummy(self) -> None:
        """A single candidate with no dummy is always selected."""
        sampler = ThompsonSampler(config=ThompsonConfig(random_seed=0))
        candidate = make_candidate("a", engaged=5, attempted=10)
        assert sampler.sample([candidate]) is candidate

    def test_single_candidate_dummy_always_wins(self) -> None:
        """A dummy with near-certain engagement beats a very poor candidate."""
        # dummy: engaged=1000, not_engaged=1 → beta sample ≈ 1.0
        # candidate: engaged=1, attempted=1000 → beta sample ≈ 0.001
        dummy = EngagementMetrics(engaged=1000, attempted=1001)
        sampler = ThompsonSampler(config=ThompsonConfig(dummy_candidate=dummy, random_seed=0))
        candidate = make_candidate("a", engaged=1, attempted=1000)
        assert sampler.sample([candidate]) is None

    def test_single_candidate_dummy_always_loses(self) -> None:
        """A very poor dummy never beats a near-certain candidate."""
        # dummy: engaged=1, not_engaged=999 → beta sample ≈ 0.001
        # candidate: engaged=1000, attempted=1001 → beta sample ≈ 1.0
        dummy = EngagementMetrics(engaged=1, attempted=1000)
        sampler = ThompsonSampler(config=ThompsonConfig(dummy_candidate=dummy, random_seed=0))
        candidate = make_candidate("a", engaged=1000, attempted=1001)
        assert sampler.sample([candidate]) is candidate


class TestThompsonSamplerMultipleCandidates:
    """Tests with multiple candidates."""

    def test_returns_one_of_candidates(self) -> None:
        """sample() always returns a candidate from the input list."""
        sampler = ThompsonSampler(config=ThompsonConfig(random_seed=42))
        candidates = [
            make_candidate("a", engaged=3, attempted=10),
            make_candidate("b", engaged=7, attempted=10),
        ]
        result = sampler.sample(candidates)
        assert result in candidates

    def test_best_candidate_wins_with_fixed_seed(self) -> None:
        """With a fixed seed, the highest-CTR candidate is consistently selected."""
        # "b" has 90% CTR vs "a" at 10%: with seed=0, "b" should win
        sampler = ThompsonSampler(config=ThompsonConfig(random_seed=0))
        candidates = [
            make_candidate("a", engaged=1, attempted=10),
            make_candidate("b", engaged=9, attempted=10),
        ]
        assert sampler.sample(candidates) is candidates[1]

    def test_reproducible_with_same_seed(self) -> None:
        """Two samplers with the same seed produce the same result."""
        candidates = [
            make_candidate("x", engaged=5, attempted=10),
            make_candidate("y", engaged=5, attempted=10),
        ]
        result1 = ThompsonSampler(config=ThompsonConfig(random_seed=7)).sample(candidates)
        result2 = ThompsonSampler(config=ThompsonConfig(random_seed=7)).sample(candidates)
        assert result1 is result2

    @pytest.mark.parametrize(
        "seed", [0, 1, 99, 12345], ids=["seed-0", "seed-1", "seed-99", "seed-12345"]
    )
    def test_result_is_always_from_input(self, seed: int) -> None:
        """For any seed, result is always from the original candidate list."""
        candidates = [make_candidate(str(i), engaged=i + 1, attempted=10) for i in range(5)]
        sampler = ThompsonSampler(config=ThompsonConfig(random_seed=seed))
        result = sampler.sample(candidates)
        assert result in candidates
