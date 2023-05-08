"""Custom Details specific Models"""
from pydantic import BaseModel


class AmoDetails(BaseModel):
    """Addon specific data to be used in Custom Details"""

    rating: str
    number_of_ratings: int


class CustomDetails(BaseModel, arbitrary_types_allowed=False):
    """Base Model for Custom Details."""

    amo: AmoDetails | None = None
