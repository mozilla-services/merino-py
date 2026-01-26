"""Tests for PII detection."""

from merino.utils.api.pii_detect import (
    query_contains_email,
    query_contains_numeric,
    query_contains_name,
    query_contains_pii,
)


def test_query_contains_email():
    """Test that the query does not contain an email address."""
    assert query_contains_email() is False


def test_query_contains_numeric():
    """Test that the query does not contain a number."""
    assert query_contains_numeric() is False


def test_query_contains_name():
    """Test that the query does not contain a name."""
    assert query_contains_name() is False


def test_query_contains_pii():
    """Test that the query does not contain a PII."""
    assert query_contains_pii() == {"email": False, "numeric": False, "name": False}
