### A supporting application for Merino

This application is designed to be run with the main Merino application for task offloading, such as search term sanitization for Firefox Suggest.

Search term sanitization looks for most commonly occurring personally identifiable information (PII) and returns a flag if it exists. This flag controls if that information is logged or collected. Detection uses the [spaCy](https://spacy.io/) natural language processing library. Please refer to that library for additional information.

(The project name "fleece" is a play on the source project "[merino](https://github.com/mozilla-services/merino-py/#about-the-name)".)

## PII / NER endpoint

`POST /api/v1/pii` with a JSON body `{"q": "<text>"}` — returns `{"pii": true}` when the input text contains a SpaCy `PERSON` named entity, otherwise `{"pii": false}`.

## Running locally

From the repo root:

```bash
uv sync --all-packages
MERINO_FLEECE_ENV=development uv run merino-fleece
```

The SpaCy NLP model (default `en_core_web_sm`) is downloaded automatically on first startup via `spacy.cli.download`. The download is cached on disk; subsequent starts skip it.

## Configuration

Dynaconf, scoped to merino-fleece. Settings live in `merino_fleece/configs/*.toml` and can be overridden by env vars prefixed `MERINO_FLEECE_`. Environment switcher: `MERINO_FLEECE_ENV` (development / testing / production). Use double underscores for nesting: `MERINO_FLEECE_PII__MODEL=en_core_web_md`.

Available knobs (under `[default.pii]`):

- `model` — one of `en_core_web_sm`, `en_core_web_md`, `en_core_web_lg` (default `en_core_web_sm`)
- `excluded_components` — SpaCy components to drop at load time (defaults to `["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"]`)
- `query_character_max` — upper bound on the `q` query parameter length (default 500)

## Tests

```bash
MERINO_FLEECE_ENV=testing uv run pytest merino-fleece/tests/unit/ --no-cov
```

The detector test will auto-download `en_core_web_sm` on first run.
