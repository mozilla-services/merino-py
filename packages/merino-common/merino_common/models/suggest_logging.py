"""Shared log data models for Suggest logging."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_serializer, model_serializer


def serialize_utc_iso(value: datetime | None) -> str | None:
    """Serialize a datetime as a UTC ISO-8601 str that BigQuery parses as a `TIMESTAMP`.

    Naive values are read as UTC rather than rejected, so a submission from an older
    client still lands as a usable timestamp.
    """
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat()


class MozlogDataModel(BaseModel):
    """Generic fields for Mozlog."""

    errno: int
    time: datetime
    path: str
    method: str

    @field_serializer("time")
    def serialize_time(self, v: datetime, **kwargs):
        """Return a datetime value as an iso formatted str."""
        return v.isoformat()


class SuggestRequestParams(BaseModel):
    """Suggest request parameters specific to Suggest logs."""

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
    # Stamped by Merino when the search term submission is created, and deliberately kept
    # out of the `web.suggest.request` record -- see `SuggestLogDataModel.serialize_flat`.
    submitted_at: datetime | None = None

    @field_serializer("submitted_at")
    def serialize_submitted_at(self, v: datetime | None, **kwargs) -> str | None:
        """Return the submission timestamp as a UTC ISO formatted str."""
        return serialize_utc_iso(v)


class SuggestLogDataModel(BaseModel):
    """Log metadata specific to Suggest logs."""

    # The Suggest search term data log is always flagged as sensitive for
    # Merino's search terms data log routing. Note that this field should
    # _not_ be used to flag the search term sanitization result.
    sensitive: bool
    mozlog: MozlogDataModel
    request_params: SuggestRequestParams

    @model_serializer
    def serialize_flat(self) -> dict[str, Any]:
        """Dump to a flat dict for backward-compatible logging output."""
        return {
            "sensitive": self.sensitive,
            **self.mozlog.model_dump(),
            # `submitted_at` belongs to the search term submission path only. This record
            # has a fixed downstream schema, and `mozlog.time` already timestamps it.
            **self.request_params.model_dump(exclude={"submitted_at"}),
        }


class SearchTermsSubmission(BaseModel):
    """Request body for submitting search terms for sanitization."""

    search_terms: list[SuggestRequestParams]


class SanitizedSearchTermLog(BaseModel):
    """Model for logging a sanitized search term.

    A subset of `SuggestRequestParams`, populated for search terms that
    merino-fleece's sanitization pass clears as non-PII.
    """

    # Always true: the record carries a raw user query, so it must be routed away
    # from the generally accessible log-inspection interfaces. Unrelated to the
    # search term sanitization verdict, which is NON_PII for every logged record.
    sensitive: bool = True
    query: str
    request_id: str  # Maps to `SuggestRequestParams.rid`.
    # Maps to `SuggestRequestParams.submitted_at`, renamed to the name the search terms
    # BigQuery dataset expects. Null for submissions that predate the field.
    timestamp: datetime | None = None
    session_id: str | None = None
    sequence_no: int | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    dma: int | None = None
    browser: str | None = None
    os_family: str | None = None
    form_factor: str | None = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, v: datetime | None, **kwargs) -> str | None:
        """Return the submission timestamp as a UTC ISO formatted str."""
        return serialize_utc_iso(v)
