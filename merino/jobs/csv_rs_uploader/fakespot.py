"""Pydantic model for MDN suggestions as they should be serialized in the
output JSON.
"""
from typing import cast

from pydantic import HttpUrl, field_validator

from merino.config import settings
from merino.jobs.csv_rs_uploader.row_major_base import RowMajorBaseSuggestion


class Suggestion(RowMajorBaseSuggestion):
    """Model for MDN suggestions as they should be serialized in the output
    JSON.
    """

    fakespot_grade: str
    product_id: str
    rating: float
    title: str
    total_reviews: int
    url: HttpUrl
    score: float

    @classmethod
    def default_collection(cls) -> str:
        """Use a different default collection, than the rest of the suggestion data

        This returns the `remote_settings.collection_fakespot` config value, which defaults to
        `fakespot-suggest-products`.
        """
        return cast(str, settings.remote_settings.collection_fakespot)

    @classmethod
    def row_major_field_map(cls) -> dict[str, str]:
        """Map field (column) names in the input CSV to suggestion property
        names in the output JSON.
        """
        return {
            "fakespot_grade": "fakespot_grade",
            "product_id": "product_id",
            "rating": "rating",
            "title": "title",
            "total_reviews": "total_reviews",
            "url": "url",
            "score": "score",
        }

    @field_validator("fakespot_grade", mode="before")
    @classmethod
    def validate_fakespot_grade(cls, value):
        """Validate fakespot_grade"""
        return cls._validate_str(value, "fakespot_grade")

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_product_id(cls, value):
        """Validate product_id"""
        return cls._validate_str(value, "product_id")

    @field_validator("title", mode="before")
    @classmethod
    def validate_title(cls, value):
        """Validate title"""
        return cls._validate_str(value, "title")
