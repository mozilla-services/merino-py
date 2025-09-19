"""A helper to create asynchronous HTTP client (via `httpx.AsyncClient`)
with common configurations.
"""

from httpx import AsyncClient, Limits, Timeout


def create_http_client(
    base_url: str = "",
    max_connections: int = 1024,
    connect_timeout: float = 1.0,
    request_timeout: float = 5.0,
    pool_timeout: float = 1.0,
    proxies: dict[str, str] | None = None,
) -> AsyncClient:
    """Crete a new `httpx.AsyncClient` with common configurations.

    Args:
      - `base_url` {str}: The base URL for this client. An empty string sets no base URL.
      - `max_connections` {int}: Max connections of the connection pool.
      - `connect_timeout` {float}: The timeout for establishing a connection to the host.
      - `request_timeout` {float}: The timeuot for handling a request to the host.
      - `pool_timeout` {float}: The timeout for acquiring a connection from the pool.
      - `proxies` {dict[str, str] | None}: A proxy dictionary for this client or no proxy is not set.
        the dictionary should look like:
        {
            "http://", "http://{your-http-proxy.com}:{port}",
            "https://", "http://{your-https-proxy.com}:{port}",
        }
    Returns:
      - {AsyncClient}: An async HTTP client.
    """
    return AsyncClient(
        base_url=base_url,
        limits=Limits(max_connections=max_connections),
        timeout=Timeout(request_timeout, connect=connect_timeout, pool=pool_timeout),
        proxies=proxies,  # type: ignore [arg-type]
    )
