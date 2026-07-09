# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Guardrails for AMP edit-distance-1 fuzzy matches.

    - Substitution: reject if the differing char is first, or the query is < 7 chars.
    - First-character insert/delete: reject.

First char inserts, substitutions, and deletes are usually too risky and are rejected
e.g. "range" -> "orange"
     "mountain" -> "fountain"
"""

from enum import StrEnum

# A single substitution on a query shorter than this is treated as too risky.
MIN_SUBSTITUTION_LEN = 7


class RejectionReason(StrEnum):
    """Why a fuzzy candidate was dropped by the guardrails"""

    FIRST_CHAR_SUBSTITUTION = "first_char_substitution"
    # corrected query has subsitution and lower length than allowed
    # also high risk, e.g. "chewy" -> "chevy"
    SHORT_SUBSTITUTION = "short_substitution"
    FIRST_CHAR_INSERT = "first_char_insert"
    FIRST_CHAR_DELETE = "first_char_delete"


class EditType(StrEnum):
    """The single edit (edit distance 1) that separates a query from a candidate."""

    TRANSPOSE = "transpose"
    SUBSTITUTE = "substitute"
    INSERT_MISSING_CHAR = "insert_missing_char"
    DELETE_EXTRA_CHAR = "delete_extra_char"
    UNKNOWN = "unknown"


def edit_type(query: str, candidate: str) -> EditType:
    """Classify the single edit that turns ``query`` into ``candidate`` (assumes ED1)."""
    if len(query) == len(candidate):
        # swithc -> switch gives mismatches [4, 5]
        mismatches = [i for i, (q, c) in enumerate(zip(query, candidate)) if q != c]
        if len(mismatches) == 2:
            i, j = mismatches
            if j == i + 1 and query[i] == candidate[j] and query[j] == candidate[i]:
                return EditType.TRANSPOSE
        return EditType.SUBSTITUTE
    if len(query) + 1 == len(candidate):
        return EditType.INSERT_MISSING_CHAR
    if len(query) == len(candidate) + 1:
        return EditType.DELETE_EXTRA_CHAR
    return EditType.UNKNOWN


def rejection_reason(query: str, candidate: str) -> RejectionReason | None:
    """Return the guardrail reason a fuzzy ``candidate`` is dropped, or ``None`` to keep."""
    match edit_type(query, candidate):
        case EditType.SUBSTITUTE:
            if query[:1] != candidate[:1]:
                return RejectionReason.FIRST_CHAR_SUBSTITUTION
            if len(query) < MIN_SUBSTITUTION_LEN:
                return RejectionReason.SHORT_SUBSTITUTION
        case EditType.INSERT_MISSING_CHAR:
            # candidate == query with a character prepended, e.g. "range" -> "orange"
            if candidate[1:] == query:
                return RejectionReason.FIRST_CHAR_INSERT
        case EditType.DELETE_EXTRA_CHAR:
            # query == candidate with a leading character removed
            if query[1:] == candidate:
                return RejectionReason.FIRST_CHAR_DELETE
    return None


def is_acceptable_fuzzy_match(query: str, candidate: str) -> bool:
    """Return ``True`` if the fuzzy ``candidate`` passes the guardrails for ``query``."""
    return rejection_reason(query, candidate) is None
