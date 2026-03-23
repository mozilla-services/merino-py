# Providers

Providers return suggestions for queries. By default, each query to the `/suggest` endpoint is dispatched asynchronously to every enabled provider. The `providers` query param can be used to specify which providers should serve the request. The provider determines whether the query is relevant to its domain and responds appropriately.

The `/providers` endpoint provides a list of available providers. See [the API docs](https://merino.services.mozilla.com/docs#/providers) for more information.

Provider documentation:

- [Flights](./flights.md)
- Finance (stocks)
- Sports
- Weather
- ADM (sponsored content)
- AMO (Addons)
- Wikipedia
- Top Picks
