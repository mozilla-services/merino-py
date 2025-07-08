# Suggest New Provider Integrations Endpoint Split

* Status: Rejected
* Deciders: Herraj Luhano, Nan Jiang, Drew Willcoxon, Chris Bellini, Temisan Iwere, Bastian Gruber
* Date: 2025-06-08

## Context and Problem Statement

We want to review the current implementation of the `suggest` endpoint and determine either to continue expanding it or to introduce new endpoints to support the upcoming new suggestion providers that are "non-standard" providers.

Standard suggest providers return results based on full or partial search queries—essentially suggesting content as the user types. Examples include `adm`, `amo`, `top_picks`, and `wikipedia`.

Non-standard suggest providers return a specific result triggered by an exact keyword match. For instance, `accuweather` provides weather details when the user enters a city name followed by the keyword weather.

### Current Implementation

Currently, all suggest providers—including third-party ones (Accuweather)—use the `/suggest/` endpoint. Here's a high-level overview of the request flow for a weather suggestion:

1. A request hits the `/suggest` endpoint.
2. The following query parameters are accepted:
   - `request`
   - `q`
   - `country`
   - `region`
   - `city`
   - `providers`
   - `client_variants`
   - `sources`
   - `request_type`

#### The `suggest()` method processes the request by:

1. Extracting `metrics_client` and `user_agent` from middleware.
2. Removing duplicate provider names (if passed via the `providers` query param).
3. Creating local variables such as `languages` and `geolocation` to be passed to the providers' `query()` methods.
4. Looping through each provider to:
   - Construct a `SuggestionRequest` object from the query params.
   - Call the provider’s `validate()` method.
   - Call the provider’s `query()` method (which does all the actual processing).
   - Add each successful async task to a list.
5. Performing additional logic and emitting per-request and per-suggestion metrics.
6. Building a `SuggestResponse` object with a list of suggestions and other metadata.
7. Adding TTL and other headers to the final response.
8. Returning an `ORJSONResponse`.

### Limitations of the Current Implementation

This implementation highlights how the `/suggest` endpoint is built to support a flexible, provider-agnostic flow. However, it comes with significant overhead—shared parsing logic, dynamic provider resolution, and assumptions like multi-suggestion responses —that don’t align well with the needs of upcoming providers. The problem statement asks whether we should continue extending this shared machinery or introduce new, purpose-built endpoints. Understanding the complexity and coupling in the current flow helps clarify why a new endpoint may offer a cleaner, more maintainable path forward for future provider integrations. See the Accuweather provider example below.

#### Accuweather Provider

The Accuweather provider currently uses this same endpoint to serve both weather suggestions and widget data. However, it's tightly coupled to all the suggest-related types, protocols, and abstractions. This coupling became especially apparent when implementing custom TTL logic for weather responses, which had to be awkwardly threaded through unrelated suggest components.

Moreover, the `SuggestResponse` type requires a suggestions list. But for weather—and likely for many new providers—we only return a single suggestion per request.

### Future Considerations

Now that we’re planning to add 5+ new providers for the Firefox search and suggest feature, we should reconsider whether this shared approach is still appropriate. These new providers will each have their own query parameters, request/response shapes, and logic for upstream API calls and formatting.

The only requirement is that the final API response must conform to the `SuggestResponse` format expected by Firefox.


## Decision Drivers

1. Separation of entities and mental model
2. Addressing the growing complex custom logic
3. Ergonomics for the client-side integration

## Considered Options

* A. Continue using the existing `/suggest` endpoint and extend it to support new providers.
* B. Create a separate endpoint for each provider, each with its own request/response handling logic.
* C. Create a single new endpoint for all non-standard providers (i.e., those that don’t follow the typical suggest flow or response shape).

## Pros & Cons of Each Option

### Option A
#### Pros
1. Consistent client interface -- No need to change frontend code or contracts; clients already know how to use `/suggest`.
2. Shared logic and infrastructure -- Leverages existing abstractions like middleware, metrics, and response formatting.

#### Cons
1. Overgeneralized interface -- Forces all providers to conform to a common structure, even when their needs (params, shape, TTL) are different.
2. Hard to scale and maintain -- Adding each new provider increases complexity and coupling, making the suggest logic harder to reason about.

### Option B
#### Pros
1. Full flexibility per provider -- Each provider can define its own request/response model and internal flow, with no need to conform to shared logic.
2. Clear separation of concerns -- Isolates logic and failures per provider, making debugging and ownership more straightforward.

#### Cons
1. Client complexity -- The frontend would need to know which endpoint to call per provider, increasing client-side branching or routing logic.
2. Maintenance overhead -- More endpoints to monitor, document, test, and version over time.

### Option C
#### Pros
1. Clean separation from the legacy `/suggest` logic -- Avoids polluting the current flow with special cases while still avoiding endpoint proliferation.
2. Balance of structure and flexibility -- A shared endpoint can still dispatch to internal handlers, allowing each provider to have tailored logic behind a unified interface.

#### Cons
1. Yet another endpoint to manage -- Slight increase in complexity at the infra/API gateway level.
2. Internal dispatching still requires careful design -- You still need to decide how to route requests internally (e.g., by provider param) and validate inputs correctly without repeating /suggest-style logic.

### Case for Option C

### 1. Encapsulation of Divergent Logic
The new providers will likely have custom logic around query parameters, upstream requests, and response formatting. Trying to shoehorn this into the existing `/suggest` flow would introduce complexity and conditionals that hurt maintainability.

A new endpoint provides a clean separation between "standard" suggest logic and custom workflows.

### 2. Avoids Tight Coupling
The existing implementation is tightly coupled to `SuggestResponse`, middleware-derived state, and other shared abstractions.

Decoupling non-standard providers from that machinery avoids repeating the friction you experienced with Accuweather (e.g., threading TTL logic and handling one-item responses in a list-based structure).

### 3. Simplifies Onboarding of Future Providers
With a flexible endpoint, you can tailor the request/response contract to match each provider's needs while maintaining a consistent response format for Firefox.

This reduces the amount of edge-case handling required and lowers the cognitive load for developers onboarding new providers.

### 4. Maintains Backward Compatibility
Keeping `/suggest` intact for legacy or conforming providers avoids breaking existing consumers.

You can gradually migrate providers to the new endpoint as needed.


## Decision Outcome

Chosen option:

* A. **Option A** -- Continue using the existing `/suggest` endpoint and extend it to support new providers.

Based on the discussion and feedback from the DISCO and Search & Suggest team engineers, we'll proceed with the current implementation using the existing `/suggest` endpoint for the new provider integrations. Since there's no pressing need to introduce a new endpoint and this approach aligns better with the client’s expectations, it makes sense to avoid unnecessary complexity for now. Down the line, we can revisit the endpoint design if needed and have a broader conversation around evolving the request/response structure to better support both legacy and new providers.
