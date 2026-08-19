# Merino-fleece

A web service providing supporting functionalities that can be integrated by **Merino** for specific tasks. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **PII Detection API**, located in @apps/fleece/merino_fleece/pii/, the backend of the `api/v1/pii` endpoint defined in @apps/fleece/merino_fleece/api/v1/pii.py. The package's `__init__.py` owns the singleton detector and thread pool along with the `detect_person` / `detect_person_batch` helpers, which are shared by the endpoint and the sanitization pass; both offload SpaCy NER to the shared thread pool.
- **Search Terms API**, the backend of the `api/v1/search-terms` endpoint defined in @apps/fleece/merino_fleece/api/v1/search_terms.py, which accepts search term submissions from **merino** for sanitization. The endpoint only enqueues; it returns 503 if the queue cannot hold the whole submission.
- **Search Terms Sanitization**, located in @apps/fleece/merino_fleece/sanitize/sanitizer.py, the pass that classifies the PII type of a batch of search terms. It runs pattern-based detection over every query before batching the survivors through SpaCy NER, and emits the terms it clears as `NON_PII` to the `web.suggest.sanitized` data log when `[default.sanitize] log_search_terms` is enabled; terms of any other PII type are never logged. Both ingestion paths below share this one pass so they classify and log identically. Configured under `[default.sanitize]`.
- **Search Terms Queue**, located in @apps/fleece/merino_fleece/message_handlers/search_terms.py, the process-wide `AsyncBatchQueue` singleton that buffers terms submitted over HTTP so sanitization runs off the request path and in batches. Owned by the app lifespan; the endpoint injects it via `Depends(get_queue)` and treats a missing queue as zero capacity.
- **Sanitization Pub/Sub Worker**, located in @apps/fleece/merino_fleece/sanitize/worker/, a separate process consuming the Pub/Sub backup channel **merino** falls back to when direct submission fails. `main.py` is an asyncio entrypoint that stands up the same dependencies as the app lifespan; the synchronous streaming pull runs on a thread and each message's callback submits its terms to the loop via `run_coroutine_threadsafe`, acking only after sanitization completes and nacking on failure or timeout. Configured under `[default.pubsub]`.
- **Sanitization Exempts**, located in @apps/fleece/merino_fleece/sanitize/exempts/, the search terms that carry no PII risk and so skip sanitization entirely. Each exempt implements the `SanitizationExempt` protocol; the package's `__init__.py` owns the process-wide registry and its lifecycle, driven by the app lifespan and by the queue worker's entrypoint. `AmpExempt` is the only one today: it fetches adMarketplace keywords from MARS per `country/form_factor` segment, refreshes them on a cron job using ETags, and serves the union as a lookup set. Configured under `[default.mars]`.

## Testing

The tests of this package is located in @apps/fleece/tests, which can be run individually.
