"""A utility module for log data creation"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_serializer
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import Message

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent


class LogDataModel(BaseModel):
    """Shared generic log data model. These fields are shared between the Request Summary Logs
    and the Suggest Logs.
    """

    errno: int
    time: datetime
    path: str
    method: str

    @field_serializer("time")
    def serialize_time(self, v: datetime, **kwargs):
        """Return a datetime value as an iso formatted str."""
        return v.isoformat()


class RequestSummaryLogDataModel(LogDataModel):
    """Log metadata specific to Request Summary."""

    agent: str | None = None
    lang: str | None = None
    querystring: dict[str, Any]
    code: int


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


def create_request_summary_log_data(
    request: Request, message: Message, dt: datetime
) -> RequestSummaryLogDataModel:
    """Create log data for API endpoints."""
    return RequestSummaryLogDataModel(
        errno=0,
        time=dt,
        agent=request.headers.get("User-Agent"),
        path=request.url.path,
        method=request.method,
        lang=request.headers.get("Accept-Language"),
        querystring=dict(request.query_params),
        code=message["status"],
    )


def create_suggest_log_data(
    request: Request, message: Message, dt: datetime
) -> SuggestLogDataModel:
    """Create log data for the suggest API endpoint."""
    location: Location = request.scope[ScopeKey.GEOLOCATION]
    user_agent: UserAgent = request.scope[ScopeKey.USER_AGENT]

    return SuggestLogDataModel(
        # General Data
        sensitive=True,
        errno=0,
        time=dt,
        # Request Data
        path=request.url.path,
        method=request.method,
        query=request.query_params.get("q"),
        code=message["status"],
        rid=Headers(scope=message)["X-Request-ID"],
        session_id=request.query_params.get("sid"),
        sequence_no=int(seq)
        if (seq := request.query_params.get("seq", "")) and seq.isdecimal()
        else None,
        client_variants=request.query_params.get("client_variants", ""),
        requested_providers=request.query_params.get("providers", ""),
        # Location Data
        country=location.country,
        region=location.region,
        city=location.city,
        dma=location.dma,
        # User Agent Data
        browser=user_agent.browser,
        os_family=user_agent.os_family,
        form_factor=user_agent.form_factor,
    )
