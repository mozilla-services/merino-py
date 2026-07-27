"""Sanitization utilities for search term submissions."""

from merino_fleece.sanitize.models import SanitizedSuggestRequest

from merino_common.models.suggest_logging import SuggestRequestParams


def sanitize_query(query: SuggestRequestParams) -> SanitizedSuggestRequest:
    """Sanitize query text; placeholder to be implemented in a follow-up ticket."""
    return SanitizedSuggestRequest(**query.model_dump(exclude={"query"}), query=query.query)
