# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the AMP fuzzy-match guardrails (`adm/fuzzy.py`)."""

import pytest

from merino.providers.suggest.adm.fuzzy import (
    EditType,
    RejectionReason,
    edit_type,
    is_acceptable_fuzzy_match,
    rejection_reason,
)


@pytest.mark.parametrize(
    ("query", "candidate", "expected"),
    [
        ("swithc", "switch", EditType.TRANSPOSE),  # adjacent swap
        ("cat", "car", EditType.SUBSTITUTE),  # single substitution
        ("abcd", "aXcY", EditType.SUBSTITUTE),  # two non-adjacent mismatches -> not a transpose
        ("range", "orange", EditType.INSERT_MISSING_CHAR),  # candidate is one char longer
        ("switchh", "switch", EditType.DELETE_EXTRA_CHAR),  # query is one char longer
        ("abc", "abcde", EditType.UNKNOWN),  # length differs by more than one
    ],
)
def test_edit_type(query: str, candidate: str, expected: EditType) -> None:
    """edit_type classifies each single-edit shape (and lengths that aren't ED1)."""
    assert edit_type(query, candidate) is expected


@pytest.mark.parametrize(
    ("query", "candidate", "expected"),
    [
        # --- rejected: risky substitutions ---
        ("mountain", "fountain", RejectionReason.FIRST_CHAR_SUBSTITUTION),
        ("chevy", "chewy", RejectionReason.SHORT_SUBSTITUTION),  # non-first sub, len < 7
        # --- rejected: first-char insert / delete ---
        ("range", "orange", RejectionReason.FIRST_CHAR_INSERT),
        ("xrange", "range", RejectionReason.FIRST_CHAR_DELETE),
        # --- kept (None) ---
        ("fragrence", "fragrance", None),  # long mid-word substitution (>= 7)
        ("swithc", "switch", None),  # transposition
        ("swich", "switch", None),  # non-first insertion
        ("switchh", "switch", None),  # end-of-word deletion
        ("abc", "abcde", None),  # unknown edit shape
    ],
)
def test_rejection_reason(query: str, candidate: str, expected: RejectionReason | None) -> None:
    """rejection_reason fires only on the two locked rules; everything else passes."""
    assert rejection_reason(query, candidate) == expected


def test_short_substitution_boundary() -> None:
    """A non-first substitution is kept at 7 chars and rejected at 6 (the MIN cutoff)."""
    # len 7, non-first substitution -> kept
    assert rejection_reason("planton", "plantox") is None
    # len 6, non-first substitution -> rejected as short
    assert rejection_reason("plants", "plantx") is RejectionReason.SHORT_SUBSTITUTION


@pytest.mark.parametrize(
    ("query", "candidate", "acceptable"),
    [
        ("fragrence", "fragrance", True),  # genuine typo -> served
        ("mountain", "fountain", False),  # intent flip -> dropped
    ],
)
def test_is_acceptable_fuzzy_match(query: str, candidate: str, acceptable: bool) -> None:
    """is_acceptable_fuzzy_match is the boolean view of rejection_reason."""
    assert is_acceptable_fuzzy_match(query, candidate) is acceptable
