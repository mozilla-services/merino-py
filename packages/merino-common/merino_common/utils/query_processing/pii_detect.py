"""Module to determine whether query contains PII."""

import re
from enum import StrEnum

AT_SIGN_PATTERN = re.compile(r"@")
NUMERIC_PATTERN = re.compile(r"\d")


class PIIType(StrEnum):
    """Enum for PII type."""

    EMAIL = "email"
    NUMERIC = "numeric"
    PERSON = "person"
    NON_PII = "non-pii"


def query_contains_email(query: str) -> bool:
    """Determine if query contains an @ sign, indicating an email address or social media handle."""
    return bool(AT_SIGN_PATTERN.search(query))


def query_contains_numeric(query: str) -> bool:
    """Determine if query contains a number."""
    return bool(NUMERIC_PATTERN.search(query))


def basic_detect(query: str) -> PIIType:
    """Determine if query contains a PII type using basic pattern matching only.

    This performs lightweight inspection for an `@` sign or a digit. It does not
    perform heavier detection such as NER / PERSON entity recognition, which is
    done by `merino-fleece`.
    """
    if query_contains_email(query):
        return PIIType.EMAIL
    elif query_contains_numeric(query):
        return PIIType.NUMERIC
    else:
        return PIIType.NON_PII
