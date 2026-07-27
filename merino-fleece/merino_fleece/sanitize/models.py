"""Internal models for fleece"""

from merino_common.models.suggest_logging import SuggestRequestParams


class SanitizedSuggestRequest(SuggestRequestParams):
    """Type hint for suggests requests which have been sanitized"""

    pass
