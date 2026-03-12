"""Unit tests for merino/optimizers/models.py"""

import pytest
from pydantic import ValidationError

from merino.optimizers.models import EngagementMetrics, ThompsonCandidate, ThompsonConfig


class TestEngagementMetrics:
    """Tests for EngagementMetrics model."""

    def test_valid(self) -> None:
        """Normal case: engaged=3, attempted=10."""
        m = EngagementMetrics(engaged=3, attempted=10)
        assert m.engaged == 3
        assert m.attempted == 10
        assert m.not_engaged == 7

    def test_adjust_engaged_zero(self) -> None:
        """engaged=0 is clamped to 1."""
        m = EngagementMetrics(engaged=0, attempted=10)
        assert m.engaged == 1

    def test_adjust_attempted_zero(self) -> None:
        """attempted=0 causes both to be clamped to 1."""
        m = EngagementMetrics(engaged=0, attempted=0)
        assert m.engaged == 1
        assert m.attempted == 1

    def test_adjust_negative(self) -> None:
        """Negative engaged is clamped to 1."""
        m = EngagementMetrics(engaged=-5, attempted=10)
        assert m.engaged == 1

    def test_not_engaged_minimum_one(self) -> None:
        """not_engaged is at least 1 even when engaged == attempted."""
        m = EngagementMetrics(engaged=5, attempted=5)
        assert m.not_engaged == 1

    def test_not_engaged_computed(self) -> None:
        """not_engaged = attempted - engaged."""
        m = EngagementMetrics(engaged=3, attempted=10)
        assert m.not_engaged == 7

    def test_check_engaged_exceeds_attempted(self) -> None:
        """Engaged > attempted raises ValidationError."""
        with pytest.raises(ValidationError):
            EngagementMetrics(engaged=5, attempted=3)

    def test_check_engaged_equals_attempted(self) -> None:
        """Engaged == attempted is valid (boundary case)."""
        m = EngagementMetrics(engaged=5, attempted=5)
        assert m.engaged == 5
        assert m.attempted == 5


class TestThompsonConfig:
    """Tests for ThompsonConfig model."""

    def test_defaults(self) -> None:
        """No args yields None defaults."""
        config = ThompsonConfig()
        assert config.dummy_candidate is None
        assert config.random_seed is None

    def test_with_dummy_candidate(self) -> None:
        """dummy_candidate stores an EngagementMetrics instance."""
        metrics = EngagementMetrics(engaged=2, attempted=10)
        config = ThompsonConfig(dummy_candidate=metrics)
        assert config.dummy_candidate == metrics

    def test_with_minimal_attempted_count(self) -> None:
        """minimal_attempted_count is stored correctly."""
        minimal_attempted_count = 1000
        config = ThompsonConfig(minimal_attempted_count=minimal_attempted_count)
        assert config.minimal_attempted_count == minimal_attempted_count

    def test_with_random_seed(self) -> None:
        """random_seed is stored correctly."""
        config = ThompsonConfig(random_seed=42)
        assert config.random_seed == 42


class TestThompsonCandidate:
    """Tests for ThompsonCandidate model."""

    def test_valid(self) -> None:
        """Basic construction with str id and EngagementMetrics."""
        metrics = EngagementMetrics(engaged=3, attempted=10)
        candidate = ThompsonCandidate(id="abc", metrics=metrics)
        assert candidate.id == "abc"
        assert candidate.metrics == metrics

    @pytest.mark.parametrize(
        "candidate_id",
        [42, "string-id", {"key": "value"}, [1, 2, 3]],
        ids=["int", "str", "dict", "list"],
    )
    def test_id_any_type(self, candidate_id: object) -> None:
        """Id field accepts any type."""
        metrics = EngagementMetrics(engaged=1, attempted=5)
        candidate = ThompsonCandidate(id=candidate_id, metrics=metrics)
        assert candidate.id == candidate_id
