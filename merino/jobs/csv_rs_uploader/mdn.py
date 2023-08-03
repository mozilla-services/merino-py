"""Pydantic model for MDN suggestions as they should be serialized in the
output JSON.
"""
from pydantic import HttpUrl, validator

from merino.jobs.csv_rs_uploader.base import BaseSuggestion

FIELD_URL = "url"
FIELD_TITLE = "title"
FIELD_DESC = "summary"
FIELD_KEYWORDS = "keyword"


class Suggestion(BaseSuggestion):
    """Model for MDN suggestions as they should be serialized in the output
    JSON.
    """

    url: HttpUrl
    title: str
    description: str
    keywords: list[str]

    @classmethod
    def csv_to_json(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON.
        """
        return {
            FIELD_URL: "url",
            FIELD_TITLE: "title",
            FIELD_DESC: "description",
            FIELD_KEYWORDS: "keywords",
        }

    @validator("title", pre=True, always=True)
    def validate_title(cls, value):
        """Validate title"""
        return cls._validate_str(cls, value, "title")

    @validator("description", pre=True, always=True)
    def validate_description(cls, value):
        """Validate description"""
        return cls._validate_str(cls, value, "description")

    @validator("keywords", pre=True, always=True)
    def validate_keywords(cls, value):
        """Validate keywords"""
        return cls._validate_keywords(cls, value, "keywords")
