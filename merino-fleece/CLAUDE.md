# Merino-fleece

A web service providing supporting functionalities that can be integrated by **Merino** for specific tasks. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **PII Detection API**, located in @merino-fleece/merino_fleece/pii/, the backend of the `api/v1/pii` endpoint defined in @merino-fleece/merino_fleece/api/v1/pii.py. The package's `__init__.py` owns the singleton detector and thread pool along with the `detect_person` / `detect_person_batch` helpers, which are shared by the endpoint and the sanitization handler; both offload SpaCy NER to the shared thread pool.
- **Search Terms API**, the backend of the `api/v1/search-terms` endpoint defined in @merino-fleece/merino_fleece/api/v1/search_terms.py, which accepts search term submissions from **merino** for sanitization. The endpoint only enqueues; it returns 503 if the queue cannot hold the whole submission.
- **Search Terms Sanitization**, located in @merino-fleece/merino_fleece/message_handlers/search_terms/, the background handler that classifies the PII type of submitted search terms off the request path. It buffers terms in an `AsyncBatchQueue` and, per batch, runs pattern-based detection over every query before batching the survivors through SpaCy NER. Terms it clears as `NON_PII` are emitted to the `web.suggest.sanitized` data log when `[default.sanitize] log_search_terms` is enabled; terms of any other PII type are never logged. Configured under `[default.sanitize]`.
- **Sanitization Exempts**, located in @merino-fleece/merino_fleece/sanitize/exempts/, the search terms that carry no PII risk and so skip sanitization entirely. Each exempt implements the `SanitizationExempt` protocol; the package's `__init__.py` owns the process-wide registry and its lifecycle, driven by the app lifespan. `AmpExempt` is the only one today: it fetches adMarketplace keywords from MARS per `country/form_factor` segment, refreshes them on a cron job using ETags, and serves the union as a lookup set. Configured under `[default.mars]`.

## Testing

The tests of this package is located in @merino-fleece/tests, which can be run individually.
