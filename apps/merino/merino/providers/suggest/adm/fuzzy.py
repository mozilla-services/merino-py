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

from merino.configs import settings

# reject single substitutions on queries shorter than this (tunable typo-FP guard)
MIN_SUBSTITUTION_LEN = settings.providers.adm.fuzzy.min_substitution_len


class RejectionReason(StrEnum):
    """Why a fuzzy candidate was dropped by the guardrails"""

    # first character replaced, e.g. "mountain" -> "fountain"
    FIRST_CHAR_SUBSTITUTION = "first_char_substitution"
    # substitution on a query shorter than MIN_SUBSTITUTION_LEN, e.g. "chewy" -> "chevy"
    SHORT_SUBSTITUTION = "short_substitution"
    # a leading character was added, e.g. "range" -> "orange"
    FIRST_CHAR_INSERT = "first_char_insert"
    # a leading character was removed, e.g. "xrange" -> "range"
    FIRST_CHAR_DELETE = "first_char_delete"


class EditType(StrEnum):
    """The single edit (edit distance 1) that separates a query from a candidate."""

    # swap two adjacent characters, e.g. "swithc" -> "switch"
    TRANSPOSE = "transpose"
    # replace one character with another, e.g. "cat" -> "car"
    SUBSTITUTE = "substitute"
    # candidate has one extra character the query lacks, e.g. "swich" -> "switch"
    INSERT_MISSING_CHAR = "insert_missing_char"
    # query has one extra character the candidate lacks, e.g. "switchh" -> "switch"
    DELETE_EXTRA_CHAR = "delete_extra_char"
    # not a single edit (lengths differ by more than one)
    UNKNOWN = "unknown"


def edit_type(query: str, candidate: str) -> EditType:
    """Classify the single edit that turns ``query`` into ``candidate`` (assumes ED1)."""
    if len(query) == len(candidate):
        for i, (q_char, c_char) in enumerate(zip(query, candidate)):
            if q_char != c_char:
                # swap the first differing char with its neighbor -> transpose if it matches
                swapped = query[:i] + query[i + 1 : i + 2] + query[i : i + 1] + query[i + 2 :]
                return EditType.TRANSPOSE if swapped == candidate else EditType.SUBSTITUTE
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
