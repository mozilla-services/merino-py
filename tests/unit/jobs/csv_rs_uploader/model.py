"""Test model"""
from pydantic import HttpUrl, field_validator

from merino.jobs.csv_rs_uploader.row_major_base import RowMajorBaseSuggestion

# The names of expected fields (columns) in the CSV input data.
FIELD_DESC = "Collection Description"
FIELD_KEYWORDS_LOW = "Low-Confidence Keywords"
FIELD_KEYWORDS_HIGH = "High-Confidence Keywords"
FIELD_TITLE = "Collection Title"
FIELD_URL = "Collection URL"


class Suggestion(RowMajorBaseSuggestion):
    """Test model"""

    url: HttpUrl
    title: str
    description: str
    lowConfidenceKeywords: list[str]
    highConfidenceKeywords: list[str]

    @classmethod
    def row_major_field_map(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON.
        """
        return {
            FIELD_URL: "url",
            FIELD_TITLE: "title",
            FIELD_DESC: "description",
            FIELD_KEYWORDS_LOW: "lowConfidenceKeywords",
            FIELD_KEYWORDS_HIGH: "highConfidenceKeywords",
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

    @field_validator("lowConfidenceKeywords", mode="before")
    @classmethod
    def validate_lowConfidenceKeywords(cls, value):
        """Validate lowConfidenceKeywords"""
        return cls._validate_keywords(value, "lowConfidenceKeywords")

    @field_validator("highConfidenceKeywords", mode="before")
    @classmethod
    def validate_highConfidenceKeywords(cls, value):
        """Validate highConfidenceKeywords"""
        return cls._validate_keywords(value, "highConfidenceKeywords")
