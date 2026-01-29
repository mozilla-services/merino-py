"""Module to determine whether query contains PII."""

import re


def query_contains_email(query: str) -> bool:
    """Determine if query contains an email address."""
    email_regex = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    return email_regex.search(query) is not None


def query_contains_numeric(query: str) -> bool:
    """Determine if query contains a number."""
    return any(ch.isdigit() for ch in query)


def query_contains_pii(query: str) -> dict[str, bool]:
    """Determine if query contains PII."""
    return {
        "email": query_contains_email(query),
        "numeric": query_contains_numeric(query),
    }
