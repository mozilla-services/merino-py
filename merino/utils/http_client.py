"""A helper to create asynchronous HTTP client (via `httpx.AsyncClient`)
with common configurations.
"""

from httpx import AsyncClient, Limits, Timeout


def create_http_client(
    base_url: str = "",
    max_connection: int = 1024,
    connect_timeout: float = 1.0,
    request_timeout: float = 5.0,
    pool_timeout: float = 1.0,
) -> AsyncClient:
    """Crete a new `httpx.AsyncClient` with common configurations.

    Args:
      - `base_url` {str}: The base URL for this client. An empty string sets no base URL.
      - `max_connections` {int}: Max connections of the connection pool.
      - `connect_timeout` {float}: The timeout for establishing a connection to the host.
      - `request_timeout` {float}: The timeuot for handling a request to the host.
      - `pool_timeout` {float}: The timeout for acquiring a connection from the pool.
    Returns:
      - {AsyncClient}: An async HTTP client.
    """
    return AsyncClient(
        base_url=base_url,
        limits=Limits(max_connections=max_connection),
        timeout=Timeout(request_timeout, connect=connect_timeout, pool=pool_timeout),
    )
