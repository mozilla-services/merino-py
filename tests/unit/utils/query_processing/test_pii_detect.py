"""Tests for PII detection."""

import pytest

from merino.utils.query_processing.pii_detect import (
    query_contains_email,
    query_contains_numeric,
    pii_inspect,
    PIIType,
)


@pytest.mark.parametrize(
    ["query", "expected"],
    [
        ("no email here", False),
        ("send me an email: test@example.com", True),
        ("not @ email .com ", False),
    ],
)
def test_query_contains_email(query, expected):
    """Test that the query does not contain an email address."""
    assert query_contains_email(query) is expected


@pytest.mark.parametrize(
    ["query", "expected"],
    [
        ("no numbers in sight", False),
        ("123 Sesame Street", True),
    ],
)
def test_query_contains_numeric(query, expected):
    """Test that the query does not contain a number."""
    assert query_contains_numeric(query) is expected


@pytest.mark.parametrize(
    ["query", "expected"],
    [
        ("no numbers in sight", PIIType.NON_PII),
        ("123 Sesame Street", PIIType.NUMERIC),
        ("email_with_numbers123@example.com", PIIType.EMAIL),
    ],
)
def test_query_contains_pii(query, expected):
    """Test that the query does not contain a PII."""
    assert pii_inspect(query) == expected
