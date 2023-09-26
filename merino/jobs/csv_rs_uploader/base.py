"""Pydantic base model for remote settings suggestions as they should be
serialized in the output JSON, plus related helpers.
"""
import re

from pydantic import BaseModel


class BaseSuggestion(BaseModel):
    """Pydantic base model for remote settings suggestions as they should be
    serialized in the output JSON.
    """

    @classmethod
    def csv_to_json(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON. Subclasses must override this method.
        """
        raise Exception("Subclass must override")

    def _validate_str(cls, value: str, name: str) -> str:
        """Validate a string value and return the validated value. Leading and
        trailing whitespace is stripped, and all whitespace is replaced with
        spaces and collapsed. Subclasses may call this method to validate
        strings in their models. To validate comma-separated keyword strings,
        use `_validate_keywords()` instead.
        """
        value = re.sub(r"\s+", " ", value.strip())
        if not value:
            raise ValueError(f"{name} must not be empty")
        return value

    def _validate_keywords(cls, value: str, name: str) -> list[str]:
        """Validate a comma-separated string of keywords and return the
        validated list of keyword strings. Each keyword is converted to
        lowercase, some non-ASCII characters are replaced with ASCII
        equivalents that users are more likely to type, leading and trailing
        whitespace is stripped, all whitespace is replaced with spaces and
        collapsed, and duplicate keywords are removed. Subclasses may call this
        method to validate keywords in their models.
        """
        value = value.lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"’", "'", value)
        keywords = [
            *filter(
                lambda kw: len(kw) > 0,
                map(str.strip, value.split(",")),
            )
        ]
        # Sort the list so tests can rely on a consistent ordering.
        keywords = sorted(list(set(keywords)))
        if not keywords or len(keywords) == 0:
            raise ValueError(f"{name} must not be empty")
        return keywords
