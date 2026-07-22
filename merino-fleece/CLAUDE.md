# Merino-fleece

A web service providing supporting functionalities that can be integrated by **Merino** for specific tasks. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **PII Detection API**, located in @merino-fleece/merino_fleece/pii/, the backend of the `api/v1/pii` endpoint defined in @merino-fleece/merino_fleece/api/v1/pii.py.
- **Search Terms API**, the backend of the `api/v1/search-terms` endpoint defined in @merino-fleece/merino_fleece/api/v1/search_terms.py, which accepts search term submissions from **merino** for sanitization.

## Testing

The tests of this package is located in @merino-fleece/tests, which can be run individually.
