# Middlwares

Merino leverages middleware for various functionalities such as logging, metrics,
parsing for geolocation & user agent, feature flags etc. Middleware is defined
in the `merino/middleware` directory.

## Caveat

We currently don't implement middleware using the middleware facilities provided
by FastAPI/Starlette as they've shown significant performance overhead, preventing
Merino from achieving the SLOs required by Firefox Suggest.

Before those performance issues get resolved in the upstream, we will be implementing
middleware for Merino through the [ASGI protocol][1]. You can also reference this
[tutorial][2] to learn more about ASGI. See Starlette's [middleware][3] document
for more details about how to write pure ASGI middlewares. Specifically, we can reuse
Starlette's data structures (`Request`, `Headers`, `QueryParams` etc.) to facilitate
the implementation.

[1]: https://asgi.readthedocs.io/en/latest/specs/www.html
[2]: https://florimond.dev/en/posts/2019/08/introduction-to-asgi-async-python-web/
[3]: https://www.starlette.io/middleware/
