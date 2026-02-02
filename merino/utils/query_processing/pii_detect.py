"""Module to determine whether query contains PII."""

import re
from enum import StrEnum

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NUMERIC_PATTERN = re.compile(r"\d")


class PIIType(StrEnum):
    """Enum for PII type."""

    EMAIL = "email"
    NUMERIC = "numeric"
    NON_PII = "non-pii"


def query_contains_email(query: str) -> bool:
    """Determine if query contains an email address."""
    return bool(EMAIL_PATTERN.search(query))


def query_contains_numeric(query: str) -> bool:
    """Determine if query contains a number."""
    return bool(NUMERIC_PATTERN.search(query))


def pii_inspect(query: str) -> PIIType:
    """Determine if query contains a PII type."""
    if query_contains_email(query):
        return PIIType.EMAIL
    elif query_contains_numeric(query):
        return PIIType.NUMERIC
    else:
        return PIIType.NON_PII
