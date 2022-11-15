"""A utility module for lag data creation"""
from datetime import datetime
from typing import Any

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import Message

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent


def create_request_summary_log_data(
    request: Request, message: Message, dt: datetime
) -> dict[str, Any]:
    """Create log data for API endpoints."""
    general_data = {
        "errno": 0,
        "time": dt.isoformat(),
    }

    request_data = {
        "agent": request.headers.get("User-Agent"),
        "path": request.url.path,
        "method": request.method,
        "lang": request.headers.get("Accept-Language"),
        "querystring": dict(request.query_params),
        "code": message["status"],
    }

    return {**general_data, **request_data}


def create_suggest_log_data(
    request: Request, message: Message, dt: datetime
) -> dict[str, Any]:
    """Create log data for the suggest API endpoint."""
    general_data = {
        "sensitive": True,
        "errno": 0,
        "time": dt.isoformat(),
    }

    request_data = {
        "path": request.url.path,
        "method": request.method,
        "query": request.query_params.get("q"),
        "code": message["status"],
        # Provided by the asgi-correlation-id middleware.
        "rid": Headers(scope=message)["X-Request-ID"],
        "session_id": request.query_params.get("sid"),
        "sequence_no": int(seq) if (seq := request.query_params.get("seq")) else None,
        "client_variants": request.query_params.get("client_variants", ""),
        "requested_providers": request.query_params.get("providers", ""),
    }

    location: Location = request.scope[ScopeKey.GEOLOCATION]
    location_data = {
        "country": location.country,
        "region": location.region,
        "city": location.city,
        "dma": location.dma,
    }

    user_agent: UserAgent = request.scope[ScopeKey.USER_AGENT]
    user_agent_data = {
        "browser": user_agent.browser,
        "os_family": user_agent.os_family,
        "form_factor": user_agent.form_factor,
    }

    return {**general_data, **request_data, **location_data, **user_agent_data}
