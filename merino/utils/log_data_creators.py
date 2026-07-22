"""A utility module for log data creation"""

from datetime import datetime

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import Message

from merino.middleware import ScopeKey
from merino.middleware.geolocation import Location
from merino.middleware.user_agent import UserAgent
from merino_common.models.suggest_logging import SuggestLogDataModel


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
        sequence_no=(
            int(seq) if (seq := request.query_params.get("seq", "")) and seq.isdecimal() else None
        ),
        client_variants=request.query_params.get("client_variants", ""),
        requested_providers=request.query_params.get("providers", ""),
        # Location Data
        country=location.country,
        region=location.regions[0] if location.regions else None,
        city=location.city,
        dma=location.dma,
        # User Agent Data
        browser=user_agent.browser,
        os_family=user_agent.os_family,
        form_factor=user_agent.form_factor,
    )
