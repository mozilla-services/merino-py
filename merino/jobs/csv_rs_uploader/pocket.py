"""Pydantic model for Pocket suggestions as they should be serialized in the
output JSON.
"""
from pydantic import HttpUrl, validator

from merino.jobs.csv_rs_uploader.base import BaseSuggestion

FIELD_URL = "Collection URL"
FIELD_TITLE = "Collection Title"
FIELD_DESC = "Collection Description"
FIELD_KEYWORDS_LOW = "Low-Confidence Keywords"
FIELD_KEYWORDS_HIGH = "High-Confidence Keywords"


class Suggestion(BaseSuggestion):
    """Model for Pocket suggestions as they should be serialized in the output
    JSON.
    """

    url: HttpUrl
    title: str
    description: str
    lowConfidenceKeywords: list[str]
    highConfidenceKeywords: list[str]

    @classmethod
    def csv_to_json(cls) -> dict[str, str]:
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

    @validator("title", pre=True, always=True)
    def validate_title(cls, value):
        """Validate title"""
        return cls._validate_str(cls, value, "title")

    @validator("description", pre=True, always=True)
    def validate_description(cls, value):
        """Validate description"""
        return cls._validate_str(cls, value, "description")

    @validator("lowConfidenceKeywords", pre=True, always=True)
    def validate_lowConfidenceKeywords(cls, value):
        """Validate lowConfidenceKeywords"""
        return cls._validate_keywords(cls, value, "lowConfidenceKeywords")

    @validator("highConfidenceKeywords", pre=True, always=True)
    def validate_highConfidenceKeywords(cls, value):
        """Validate highConfidenceKeywords"""
        return cls._validate_keywords(cls, value, "highConfidenceKeywords")
