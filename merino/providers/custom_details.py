"""Custom Details specific Models"""
from pydantic import BaseModel


class AmoDetails(BaseModel):
    """Addon specific fields."""

    rating: str
    number_of_ratings: int
    guid: str


class CustomDetails(BaseModel, arbitrary_types_allowed=False):
    """Contain references to custom fields for each provider.
    This object uses the provider name as the key, and references custom schema models.
    Please consult the custom details object for more information.
    """

    amo: AmoDetails | None = None
