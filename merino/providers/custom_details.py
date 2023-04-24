"""Custom Details specific Models"""
from pydantic import BaseModel


class AddonsDetails(BaseModel):
    """Addon specific data to be used in Custom Details"""

    rating: str


class CustomDetails(BaseModel):
    """Base Model for Custom Details."""

    addons: AddonsDetails | None = None
