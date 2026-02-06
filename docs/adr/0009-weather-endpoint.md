# Dedicated Weather Endpoint to Serve New Tab Weather Widget Requests

* Status: proposed  
* Deciders: DISCO, Home & New Tab, Search & Suggest teams
* Date: 2026-02-06

**Technical Story:** Serve New Tab Weather Widget requests from a dedicated endpoint instead of `v1/suggest` to reduce coupling and allow widget-specific caching/TTL and roadmap expansion (hourly forecasts, alerts).

---

## Context and Problem Statement

The `v1/suggest` endpoint was originally designed for Firefox search bar suggestions, but has expanded over time to serve multiple provider-backed experiences (weather, stocks, flights, sports, etc.). The New Tab Weather Widget has different product requirements (including a roadmap for hourly forecasts and alerts), different request volume and frequency patterns, and different caching/TTL needs than the search bar suggestions. Additionally, the weather widget on the new tab uses the same code as search and suggest to request weather data.

How should we separate New Tab Weather Widget weather requests from `v1/suggest` to reduce coupling, improve flexibility (features and caching), and keep client engineering simple?

---

## Decision Drivers

1. **Caching / TTL control** -- **Curcial Requirement**  
   Allow weather-specific cache TTLs aligned with HTTP response caching headers. This will allow us to control the number of live requests made to the Accuweather API to manage the monthly quota. This is very important to keep the costs down since we plan to introduce this widget in new regions which means the total number of requests will increase.

2. **Decouple client needs**  
   Search bar and new tab have different behaviors, performance expectations, and product needs.

3. **Future extensibility**  
   Support hourly forecasts, alerts, and other weather expansions without growing `v1/suggest` further.

4. **Client simplicity**  
   Keep client integration straightforward and stable.

5. **Operational clarity**  
   Clearer ownership, metrics, and planning per endpoint and client.

6. **Backward compatibility**  
   Avoid breaking existing search bar consumers and provider integrations.

---

## Considered Options

* **A.** Keep using `v1/suggest` for weather (status quo), continue adding weather capabilities there.
* **B.** Create resource-oriented endpoints under `v1/weather/*`  
  (e.g., `v1/weather/weather-report`, `v1/weather/hourly-forecasts`, `v1/weather/alerts`).
* **C.** Create a single `v1/weather` endpoint with query-driven expansions  
  (e.g., `v1/weather?include=hourly,alerts`) while returning the base report by default.
* **D.** Create a dedicated product-scoped endpoint  
  (e.g., `v1/newtab/weather`) explicitly tied to the New Tab experience.

---

## Pros and Cons of each option

### A. Keep weather in `v1/suggest`

**Pros**
* No client migration required.
* Avoids introducing new endpoints or contracts in the short term.

**Cons**
* Continues tight coupling between search bar and new tab requirements.
* Difficult to apply widget-specific caching/TTL and HTTP headers without impacting search bar behavior.
* `v1/suggest` continues to grow in scope and operational complexity.
---

### B. Multiple endpoints under `v1/weather/*` (Recommended based on the crucial requirement above)

**Pros**
* Clear separation of concerns by resource and capability (Better alignment with REST/resource-oriented design).
* Explicit and independent caching semantics per endpoint (e.g., hourly vs alerts).
* Simpler server-side logic:
Handlers don’t need branching logic based on include= flags. Each endpoint can be implemented, tested, and optimized independently.
* Response payload shape does not depend on `Suggestion` type.

**Cons**
* Client will have to make more than one request depending on the weather data required.
* More client complexity: The client has to coordinate parallel fetches, retries, partial failures (e.g., report succeeds but alerts fail), and loading states.
* More endpoints to document, monitor, version, and operate.

---

### C. Single `v1/weather` endpoint with `include=` expansions

**Pros**
* Simple client integration: base report by default, opt-in expansions as needed.
* One request can serve the widget UI while still allowing selective feature growth.
* Keeps endpoint surface area small while remaining extensible.

**Cons**
* Behaviour is somewhat similar to the existing `v1/suggest` behaviour.
* Cannot use different cache-control headers for different types of data. Have to use a minimum TTL to represent all types of data in the response.
* More complex server-side logic for assembling partial responses and setting appropriate headers.

---

### D. Product-scoped endpoint (`v1/newtab/weather`)

**Pros**
* Very clear ownership and intent: explicitly tied to the New Tab Weather Widget.
* Maximum freedom to optimize behavior and performance for widget-specific needs.

**Cons**
* Risk of duplicating weather-domain APIs across products over time.
* Feels like a bit of an overkill at this point.
* Implies that only new tab can access this endpoint and can cause confusion among different clients in the future.
* May lead to API fragmentation if other products follow the same pattern.

---


## Additional Suggestions and Recommendations

**Option B** Seems like the best option for the problems we are trying to solve right now. It allows us flexibility with cache TTLs, simpler logic and implementation without having to do query/request param parsing. It also allows us to grow the weather functionality with different types weather data easily, without creating more coupling with the `v1/suggest` endpoint.

### Implementation Plan

* Keep `v1/suggest` behavior stable. i.e it will serve the current weather report suggestion response (used by search bar and current weather widget).
* Create a new endpoint `v1/weather/hourly-forecasts` to serve hourly forecasts first.
* Eventually add functionality to serve the existing weather report and location completions via `v1/weather/*`. This will allow the new tab client engineers to move off of using the search and suggest code for the weather widget completely.
* Expand functionality for new weather features (e.g alerts) under the new endpoint.
