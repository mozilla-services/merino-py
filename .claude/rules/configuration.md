---
paths:
  - "merino/configs/**"
---

# Configuration System

Dynaconf loads TOML files from `merino/configs/app_configs/` based on `MERINO_ENV`:

- `default.toml` (40KB, all settings with defaults)
- `development.toml` (pretty logging, DEBUG, 600s timeout, test API keys)
- `testing.toml` (test backends, 0.5s timeout, disabled providers)
- `ci.toml` (test backends, prevents accidental API calls)
- `stage.toml` / `production.toml` (real backends, mozlog, 0.2s timeout, Google ADC auth)

## Env var override pattern

`MERINO_{SECTION}__{KEY}=value` (double underscore separates nesting levels, all uppercase).

Examples:
- `MERINO_LOGGING__LEVEL=DEBUG`
- `MERINO_PROVIDERS__WIKIPEDIA__ES_URL=http://localhost:9200`
- `MERINO_ACCUWEATHER__API_KEY=secret`

## Adding provider config

Add two sections to `default.toml`:
- `[default.providers.myprovider]` - `type`, `backend`, `enabled_by_default`, `score`, `query_timeout_sec`, `cache`
- `[default.myprovider]` - API keys, URLs, provider-specific settings

## Validators

200+ validators in `merino/configs/__init__.py` enforce types, ranges, and environment-specific constraints. Production enforces `query_timeout_sec <= 0.2` and `skip_gcp_client_auth = true`.

## Feature flags

Separate Dynaconf instance loading from `merino/configs/flags/`. Flags have `enabled` (0.0-1.0) and `scheme` (random/session). Usage: `flags.is_enabled("feature-name", bucket_for=session_id)`.
