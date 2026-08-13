# Merino-fleece

A web service providing supporting functionalities that can be integrated by **Merino** for specific tasks. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **PII Detection API**, located in @merino-fleece/merino_fleece/pii/, the backend of the `api/v1/pii` endpoint defined in @merino-fleece/merino_fleece/api/v1/pii.py. The package's `__init__.py` owns the singleton detector and thread pool along with the `detect_person` / `detect_person_batch` helpers, which are shared by the endpoint and the sanitization handler; both offload SpaCy NER to the shared thread pool.
- **Search Terms API**, the backend of the `api/v1/search-terms` endpoint defined in @merino-fleece/merino_fleece/api/v1/search_terms.py, which accepts search term submissions from **merino** for sanitization. The endpoint only enqueues; it returns 503 if the queue cannot hold the whole submission.
- **Search Terms Sanitization**, located in @merino-fleece/merino_fleece/message_handlers/search_terms/, the background handler that classifies the PII type of submitted search terms off the request path. It buffers terms in an `AsyncBatchQueue` and, per batch, runs pattern-based detection over every query before batching the survivors through SpaCy NER. Configured under `[default.sanitize]`.

## Testing

The tests of this package is located in @merino-fleece/tests, which can be run individually.
