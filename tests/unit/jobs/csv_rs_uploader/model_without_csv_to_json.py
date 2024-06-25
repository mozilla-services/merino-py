"""Test model without Suggestion.csv_to_json() implementation"""

from merino.jobs.csv_rs_uploader.base import BaseSuggestion


class Suggestion(BaseSuggestion):
    """Test model without csv_to_json() implementation"""

    pass
