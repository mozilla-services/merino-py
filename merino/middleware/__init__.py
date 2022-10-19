"""Merino middlewares"""


class ScopeKey:
    """Keys into the ASGI scope dict"""

    GEOLOCATION = "merino_geolocation"
    USER_AGENT = "merino_user_agent"
