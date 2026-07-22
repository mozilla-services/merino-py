"""Shared log data models for Suggest logging."""

from datetime import datetime

from pydantic import BaseModel, field_serializer


class LogDataModel(BaseModel):
    """Shared generic log data model."""

    errno: int
    time: datetime
    path: str
    method: str

    @field_serializer("time")
    def serialize_time(self, v: datetime, **kwargs):
        """Return a datetime value as an iso formatted str."""
        return v.isoformat()


class SuggestLogDataModel(LogDataModel):
    """Log metadata specific to Suggest logs."""

    sensitive: bool
    query: str | None = None
    code: int
    rid: str  # Provided by the asgi-correlation-id middleware.
    session_id: str | None = None
    sequence_no: int | None = None
    client_variants: str
    requested_providers: str
    country: str | None = None
    region: str | None = None
    city: str | None = None
    dma: int | None = None
    browser: str
    os_family: str
    form_factor: str


class SearchTermsSubmission(BaseModel):
    """Request body for submitting search terms for sanitization."""

    search_terms: list[SuggestLogDataModel]
