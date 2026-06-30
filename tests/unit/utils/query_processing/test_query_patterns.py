"""Unit tests for query pattern config loading and compilation."""

import logging

import pytest

from merino.utils.query_processing.query_patterns import (
    MAX_REGEX_LENGTH,
    QueryPatternMatcher,
    build_query_pattern_matcher,
    match_query,
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
    assert tuple(pattern.id for pattern in matcher.patterns) == (
        "sports_v1",
        "flights_v1",
    )
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


@pytest.fixture()
def two_pattern_matcher() -> QueryPatternMatcher:
    """Build a matcher with sports and flights patterns for reuse across match_query tests."""
    matcher = build_query_pattern_matcher(
        enabled=True,
        sample_rate=1.0,
        patterns=[
            {"id": "sports_v1", "regex": r"\b(nba|nfl|mlb|nhl|soccer)\b"},
            {"id": "flights_v1", "regex": r"\b(flight|airline|airport)\b"},
        ],
    )
    assert matcher is not None
    return matcher


def test_match_query_no_match(two_pattern_matcher: QueryPatternMatcher) -> None:
    """Test that a query with no pattern matches returns an empty tuple."""
    assert match_query(two_pattern_matcher, "weather in toronto") == ()


def test_match_query_one_match(two_pattern_matcher: QueryPatternMatcher) -> None:
    """Test that a query matching exactly one pattern returns that pattern's id."""
    assert match_query(two_pattern_matcher, "nba scores tonight") == ("sports_v1",)


def test_match_query_multiple_matches(two_pattern_matcher: QueryPatternMatcher) -> None:
    """Test that a query matching multiple patterns returns all matching ids."""
    result = match_query(two_pattern_matcher, "nba airport shuttle")
    assert result == ("sports_v1", "flights_v1")


def test_match_query_case_insensitive(two_pattern_matcher: QueryPatternMatcher) -> None:
    """Test that matching is case-insensitive regardless of query casing."""
    assert match_query(two_pattern_matcher, "NBA Finals") == ("sports_v1",)
    assert match_query(two_pattern_matcher, "FLIGHT deals") == ("flights_v1",)


def test_match_query_empty_string(two_pattern_matcher: QueryPatternMatcher) -> None:
    """Test that an empty query returns an empty tuple without evaluating any patterns."""
    assert match_query(two_pattern_matcher, "") == ()


def test_match_query_returns_ids_not_query_text(
    two_pattern_matcher: QueryPatternMatcher,
) -> None:
    """Test that the return value contains only pattern IDs, never substrings of the query."""
    result = match_query(two_pattern_matcher, "nba scores")
    assert all(isinstance(r, str) for r in result)
    assert "nba" not in result
    assert "scores" not in result
