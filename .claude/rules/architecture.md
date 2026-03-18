# Architecture Overview

## Three Subsystems

1. **Suggest API** (`merino/providers/suggest/`) - FastAPI service answering Firefox address bar queries. 10 providers (ADM, AMO, Wikipedia, Weather, Top Picks, Finance, Yelp, FlightAware, Sports, Geolocation) each implement `BaseProvider` with `initialize()`, `query()`, `shutdown()`. Providers are registered in `merino/providers/suggest/manager.py` via `ProviderType` enum and factory function.

2. **Curated Recommendations** (`merino/curated_recommendations/`) - Separate subsystem for Firefox NewTab. Fetches articles from Pocket Corpus API (GraphQL), ranks with Thompson Sampling using engagement data + Bayesian priors from GCS. Has its own backends (corpus, engagement, prior, ML), rankers, layouts, and experiments. Completely independent from Suggest.

3. **Jobs** (`merino/jobs/`) - Airflow data pipelines invoked via `merino-jobs` CLI. Jobs populate data that providers serve.

## Job-Provider Relationships

If provider data seems stale, check if the corresponding job has run:

- **Wikipedia Indexer** job -> **Wikipedia** provider (via Elasticsearch)
- **Navigational Suggestions** job -> **Top Picks** provider (via GCS `top_picks.json` manifest)
- **Polygon Ingestion** job -> **Finance** provider (via GCS manifest)
- **FlightAware Schedules** job -> **FlightAware** provider (via Redis/GCS)
- **Sports Data** job -> **Sports** provider (via Elasticsearch)
- **AMO Uploader** job -> **AMO** provider (via Remote Settings)

## Key Infrastructure

- **Circuit breakers** (`merino/governance/`): Weather and FlightAware providers use circuit breakers. 10 failures -> open -> 30s recovery -> fallback returns `[]`.
- **SyncedGcsBlob** (`merino/utils/synced_gcs_blob.py`): Periodically pulls GCS blob, calls callback on change. Used by curated_recommendations backends.
- **Cron jobs** (`merino/utils/cron.py`): Background refresh for providers (ADM, Weather, Top Picks, Finance, etc.).
- **Blocklists** (`merino/utils/blocklists.py`): `TOP_PICKS_BLOCKLIST`, `WIKIPEDIA_TITLE_BLOCKLIST`, `FAKESPOT_CSV_UPLOADER_BLOCKLIST`.
- **mozilla-merino-ext**: Compiled Rust extension providing `AmpIndexManager` for ADM provider. Import: `from moz_merino_ext.amp import AmpIndexManager`.
- **Remote Settings** (Kinto): Mozilla's content delivery. Jobs upload suggestions, Firefox clients sync them. Production server: `https://firefox.settings.services.mozilla.com/v1`.

## App Startup (merino/main.py)

Lifespan context manager runs: `configure_logging()` -> `configure_sentry()` -> `configure_metrics()` -> `init_providers()` -> `init_manifest_provider()` -> `init_curated_recommendations()` -> `governance.start()`. Shutdown reverses.

## Middleware Stack (order matters)

CORSMiddleware -> MetricsMiddleware -> CorrelationIdMiddleware -> FeatureFlagsMiddleware -> GeolocationMiddleware -> UserAgentMiddleware -> LoggingMiddleware. LoggingMiddleware depends on CorrelationId and Geolocation.
