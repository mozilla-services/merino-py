"""Pydantic model for MDN suggestions as they should be serialized in the
output JSON.
"""
from pydantic import HttpUrl, field_validator

from merino.jobs.csv_rs_uploader.row_major_base import RowMajorBaseSuggestion

FIELD_URL = "url"
FIELD_TITLE = "title"
FIELD_DESC = "summary"
FIELD_KEYWORDS = "keyword"


class Suggestion(RowMajorBaseSuggestion):
    """Model for MDN suggestions as they should be serialized in the output
    JSON.
    """

    url: HttpUrl
    title: str
    description: str
    keywords: list[str]

    @classmethod
    def row_major_field_map(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON.
        """
        return {
            FIELD_URL: "url",
            FIELD_TITLE: "title",
            FIELD_DESC: "description",
            FIELD_KEYWORDS: "keywords",
        }

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value):
        """Validate title"""
        return cls._validate_str(value, "title")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value):
        """Validate description"""
        return cls._validate_str(value, "description")

    @field_validator("keywords", mode="before")
    @classmethod
    def validate_keywords(cls, value):
        """Validate keywords"""
        return cls._validate_keywords(value, "keywords")
