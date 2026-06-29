"""Unit tests for query pattern config loading and compilation."""

import logging

import pytest

from merino.utils.query_processing.query_patterns import (
    MAX_REGEX_LENGTH,
    build_query_pattern_matcher,
)

QUERY_PATTERNS_LOGGER = "merino.utils.query_processing.query_patterns"


def test_build_query_pattern_matcher_disabled() -> None:
    """A disabled feature should not build a matcher."""
    matcher = build_query_pattern_matcher(
        enabled=False,
        sample_rate=1.0,
        patterns=[{"id": "sports_v1", "regex": "nba"}],
    )

    assert matcher is None


def test_build_query_pattern_matcher_zero_sample_rate() -> None:
    """A non-positive sample rate should avoid all matcher work."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=0.0,
        patterns=[{"id": "sports_v1", "regex": "nba"}],
    )

    assert matcher is None


def test_build_query_pattern_matcher_empty_patterns() -> None:
    """An empty pattern set should not build a matcher."""
    matcher = build_query_pattern_matcher(enabled=True, sample_rate=1.0, patterns=[])

    assert matcher is None


def test_build_query_pattern_matcher_clamps_sample_rate() -> None:
    """A sample rate above 1.0 should be clamped to 1.0."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=5.0,
        patterns=[{"id": "sports_v1", "regex": "nba"}],
    )

    assert matcher is not None
    assert matcher.sample_rate == 1.0


def test_build_query_pattern_matcher_skips_invalid_entries() -> None:
    """Invalid ids, regexes, and non-mapping entries are skipped, valid ones kept."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=1.0,
        patterns=[
            "not-a-mapping",
            {"id": "sports-v1", "regex": "nba"},  # hyphen is not a valid id
            {"id": "Sports_v1", "regex": "nba"},  # uppercase is not a valid id
            {"id": "broken_v1", "regex": "["},  # unparseable regex
            {"id": "empty_v1", "regex": ""},  # empty regex
            {"id": "huge_v1", "regex": "a" * (MAX_REGEX_LENGTH + 1)},  # oversized regex
            {"id": "missing_regex_v1"},  # no regex key
            {"id": "sports_v1", "regex": "nba"},  # the only valid entry
        ],
    )

    assert matcher is not None
    assert tuple(pattern.id for pattern in matcher.patterns) == ("sports_v1",)


def test_build_query_pattern_matcher_keeps_multiple_valid_patterns() -> None:
    """Every valid pattern is retained, in order, with a case-insensitive regex."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=0.5,
        patterns=[
            {"id": "sports_v1", "regex": r"\b(nba|nfl)\b"},
            {"id": "flights_v1", "regex": r"\b(flight|airport)\b"},
        ],
    )

    assert matcher is not None
    assert tuple(pattern.id for pattern in matcher.patterns) == ("sports_v1", "flights_v1")
    assert matcher.patterns[0].regex.search("NBA scores") is not None


def test_build_query_pattern_matcher_deduplicates_by_id_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later definition for an id replaces the earlier one and is warned about."""
    with caplog.at_level(logging.WARNING, logger=QUERY_PATTERNS_LOGGER):
        matcher = build_query_pattern_matcher(
            enabled=True,
            sample_rate=1.0,
            patterns=[
                {"id": "sports_v1", "regex": "nba"},
                {"id": "sports_v1", "regex": "nfl"},
            ],
        )

    assert matcher is not None
    assert tuple(pattern.id for pattern in matcher.patterns) == ("sports_v1",)
    assert matcher.patterns[0].regex.search("nfl") is not None
    assert matcher.patterns[0].regex.search("nba") is None
    assert any("duplicate id" in record.message for record in caplog.records)


def test_build_query_pattern_matcher_identical_duplicate_is_quiet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An identical duplicate id collapses to one entry without a warning."""
    with caplog.at_level(logging.WARNING, logger=QUERY_PATTERNS_LOGGER):
        matcher = build_query_pattern_matcher(
            enabled=True,
            sample_rate=1.0,
            patterns=[
                {"id": "sports_v1", "regex": "nba"},
                {"id": "sports_v1", "regex": "nba"},
            ],
        )

    assert matcher is not None
    assert len(matcher.patterns) == 1
    assert caplog.records == []


def test_build_query_pattern_matcher_all_invalid_returns_none() -> None:
    """A config with only invalid patterns yields no matcher rather than raising."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=1.0,
        patterns=[{"id": "bad-id", "regex": "nba"}, {"id": "broken_v1", "regex": "("}],
    )

    assert matcher is None
