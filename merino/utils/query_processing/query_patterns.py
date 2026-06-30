"""Query pattern matching for aggregate suggest metrics.

PRIVACY CONTRACT:
- Emits only ``merino.query_pattern.match`` (attributes ``pattern_id``, ``matched``,
  ``source``) and ``merino.query_pattern.error`` (attribute ``source``).
- Never emits raw query text, the matched substring, or the regex source.
- ``pattern_id`` is operator-controlled and low-cardinality (``PATTERN_ID_RE``), so a
  metric series identifies a query *category*, never a search.
- Matching runs on the raw query in memory before PII suppression; only aggregate
  counters leave the process.
- Fail-safe: an invalid config disables the matcher rather than failing startup.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

logger = logging.getLogger(__name__)

# A pattern id is the only operator-supplied value that reaches metrics, so it is
# constrained to a short, lowercase token to keep metric cardinality bounded and
# free of anything derived from user input.
PATTERN_ID_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

MAX_REGEX_LENGTH: Final = 500


@dataclass(frozen=True, slots=True)
class QueryPattern:
    """A compiled query pattern paired with a metric-safe identifier."""

    id: str
    regex: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class QueryPatternMatcher:
    """Validated set of patterns to evaluate, with the request sampling rate."""

    patterns: tuple[QueryPattern, ...]
    sample_rate: float


def build_query_pattern_matcher(
    *,
    enabled: bool,
    sample_rate: float,
    patterns: Sequence[object],
) -> QueryPatternMatcher | None:
    """Build a query pattern matcher from configuration.

    Returns ``None`` when the feature is disabled, the sample rate is non-positive,
    or no valid patterns remain after compilation, so callers can treat a missing
    matcher as a clean no-op. Invalid pattern entries are logged and skipped rather
    than raised, so a temporary measurement config cannot break Merino startup or
    serving.
    """
    if not enabled or sample_rate <= 0:
        return None

    compiled_patterns = _iter_patterns(patterns)
    if not compiled_patterns:
        logger.warning("Query pattern matching enabled without valid patterns")
        return None

    return QueryPatternMatcher(
        patterns=compiled_patterns,
        sample_rate=min(sample_rate, 1.0),
    )


def _iter_patterns(patterns: Sequence[object]) -> tuple[QueryPattern, ...]:
    # Patterns are keyed by id; a later definition wins so a study can override an
    # earlier entry. A duplicate id whose regex differs is almost always a config
    # mistake, so surface it as a warning rather than silently dropping one.
    deduped: dict[str, QueryPattern] = {}
    for entry in patterns:
        if not isinstance(entry, Mapping):
            logger.warning("Ignoring query pattern with invalid config entry")
            continue

        pattern = _compile_pattern(cast(Mapping[str, object], entry))
        if pattern is None:
            continue

        existing = deduped.get(pattern.id)
        if existing is not None and existing.regex.pattern != pattern.regex.pattern:
            logger.warning(
                "Overriding query pattern with duplicate id and differing regex",
                extra={"pattern_id": pattern.id},
            )
        deduped[pattern.id] = pattern
    return tuple(deduped.values())


def _compile_pattern(entry: Mapping[str, object]) -> QueryPattern | None:
    pattern_id = entry.get("id")
    expression = entry.get("regex")

    if not isinstance(pattern_id, str) or not PATTERN_ID_RE.fullmatch(pattern_id):
        logger.warning("Ignoring query pattern with invalid id")
        return None

    if not isinstance(expression, str) or not expression or len(expression) > MAX_REGEX_LENGTH:
        logger.warning(
            "Ignoring query pattern with invalid regex",
            extra={"pattern_id": pattern_id},
        )
        return None

    try:
        return QueryPattern(id=pattern_id, regex=re.compile(expression, re.IGNORECASE))
    except re.error:
        logger.warning(
            "Ignoring query pattern with unparseable regex",
            extra={"pattern_id": pattern_id},
        )
        return None


def match_query(matcher: QueryPatternMatcher, query: str) -> tuple[str, ...]:
    """Return the IDs of all patterns that match *query*."""
    if not query:
        return ()
    return tuple(p.id for p in matcher.patterns if p.regex.search(query))
