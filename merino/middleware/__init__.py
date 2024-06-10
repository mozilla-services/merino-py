"""Merino middlewares"""

from enum import Enum, unique


@unique
class ScopeKey(str, Enum):
    """Keys into the ASGI scope dict"""

    GEOLOCATION = "merino_geolocation"
    USER_AGENT = "merino_user_agent"
    FEATURE_FLAGS: str = "merino_feature_flags"
    METRICS_CLIENT: str = "merino_metrics_client"
