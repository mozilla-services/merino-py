"""Emission utilities for search term submissions."""

from merino_fleece.sanitize.models import SanitizedSuggestRequest


def emit_sanitized_query(submission: SanitizedSuggestRequest) -> None:
    """Emit search terms for downstream processing and storage;
    placeholder to be implemented in a follow-up ticket.
    """
    pass
