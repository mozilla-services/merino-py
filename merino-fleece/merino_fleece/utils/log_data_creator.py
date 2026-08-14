"""A utility module for log data creation."""

from merino_common.models.suggest_logging import (
    SanitizedSearchTermLog,
    SuggestRequestParams,
)


def create_search_term_log(params: SuggestRequestParams) -> SanitizedSearchTermLog:
    """Create log data for a search term that sanitization cleared as non-PII."""
    return SanitizedSearchTermLog(
        query=params.query or "",
        request_id=params.rid,
        session_id=params.session_id,
        sequence_no=params.sequence_no,
        country=params.country,
        region=params.region,
        city=params.city,
        dma=params.dma,
        browser=params.browser,
        os_family=params.os_family,
        form_factor=params.form_factor,
    )
