"""Pydantic model for row-major based suggestion as they should be serialized in
the output JSON.
"""

from merino.jobs.csv_rs_uploader import MissingFieldError
from merino.jobs.csv_rs_uploader.base import BaseSuggestion


class RowMajorBaseSuggestion(BaseSuggestion):
    """Model for suggestions created from row-major based CSV content as they
    should be serialized in the output JSON.
    """

    @classmethod
    def csv_to_suggestions(cls, csv_reader) -> list[BaseSuggestion]:
        """Convert row-major based CSV content to Suggestions."""
        field_map = cls.row_major_field_map()
        suggestions: list = []
        for row in csv_reader:
            for field in field_map.keys():
                if field not in row:
                    raise MissingFieldError(f"Expected CSV field `{field}` is missing")
            kwargs = {prop: row[field] for field, prop in field_map.items()}
            suggestions.append(cls(**kwargs))
        return suggestions

    @classmethod
    def row_major_field_map(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON. Subclasses must override this method.
        """
        raise Exception("Subclass must override")
