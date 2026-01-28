"""Module to determine whether query contains PII."""


def query_contains_email() -> bool:
    """Determine if query contains an email address."""
    return False


def query_contains_numeric() -> bool:
    """Determine if query contains a number."""
    return False


def query_contains_name() -> bool:
    """Determine if query contains a name."""
    return False


def query_contains_pii() -> dict[str, bool]:
    """Determine if query contains PII."""
    return {
        "email": query_contains_email(),
        "numeric": query_contains_numeric(),
        "name": query_contains_name(),
    }
