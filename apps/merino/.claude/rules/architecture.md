# Architecture Overview

## Subsystems

1. **Suggest API** (`apps/merino/merino/providers/suggest/`) - FastAPI service answering Firefox address bar queries. 10 providers (ADM, AMO, Wikipedia, Weather, Top Picks, Finance, Yelp, FlightAware, Sports, Geolocation) each implement `BaseProvider` with `initialize()`, `query()`, `shutdown()`. Providers are registered in `apps/merino/merino/providers/suggest/manager.py` via `ProviderType` enum and factory function.

2. **Curated Recommendations** (`apps/merino/merino/curated_recommendations/`) - Separate subsystem for Firefox NewTab. Fetches articles from Pocket Corpus API (GraphQL), ranks with Thompson Sampling using engagement data + Bayesian priors from GCS. Has its own backends (corpus, engagement, prior, ML), rankers, layouts, and experiments. Completely independent from Suggest.

3. **Jobs** (`apps/merino/merino/jobs/`) - Airflow data pipelines invoked via `merino-jobs` CLI. Jobs populate data that providers serve.

4. **Games API** (`apps/merino/merino/providers/games/`), the backend of the `api/v1/games/*` endpoints defined in @apps/merino/merino/web/api_v1.py.

5. **Image Manifest API** (`apps/merino/merino/providers/manifest/`), the backend of the `api/v1/manifest` endpoint defined in @apps/merino/merino/web/api_v1.py.

6. **RSS API** (`apps/merino/merino/providers/rss/`), the backend of the `api/v1/rss/*` endpoints defined in @apps/merino/merino/web/api_v1.py.

## Job-Provider Relationships

If provider data seems stale, check if the corresponding job has run:

- **Wikipedia Indexer** job -> **Wikipedia** provider (via Elasticsearch)
- **Navigational Suggestions** job -> **Top Picks** provider (via GCS `top_picks.json` manifest)
- **Polygon Ingestion** job -> **Finance** provider (via GCS manifest)
- **FlightAware Schedules** job -> **FlightAware** provider (via Redis/GCS)
- **Sports Data** job -> **Sports** provider (via Elasticsearch)
- **AMO Uploader** job -> **AMO** provider (via Remote Settings)

## Other Components

- **Circuit breakers** (`apps/merino/merino/governance/`): Weather, FlightAware, and Finance (polygon) providers use circuit breakers. 10 failures -> open -> 30s recovery -> fallback returns `[]`.
- **SyncedGcsBlob** (`apps/merino/merino/utils/synced_gcs_blob.py`): Periodically pulls GCS blob, calls callback on change. Used by curated_recommendations backends.
- **Cron jobs** (`packages/merino-common/merino_common/utils/cron.py`): Background refresh for providers (ADM, Weather, Top Picks, Finance, etc.).
- **Blocklists** (`apps/merino/merino/utils/blocklists.py`): `TOP_PICKS_BLOCKLIST`, `WIKIPEDIA_TITLE_BLOCKLIST`.
- **mozilla-merino-ext**: Compiled Rust extension providing `AmpIndexManager` for ADM provider. Import: `from moz_merino_ext.amp import AmpIndexManager`.
- **Remote Settings** (Kinto): Mozilla's content delivery. Jobs upload suggestions, Firefox clients sync them. Production server: `https://firefox.settings.services.mozilla.com/v1`.

## App Startup & Shutdown (apps/merino/merino/main.py)

Merino can be configured to be run in various modes via the configuration `runtime.mode`. Each mode could define its own FastAPI lifespan events (startup & shutdown) via `create_lifespan()` in @apps/merino/merino/main.py.

## Middleware Stack (order matters)

CORSMiddleware -> MetricsMiddleware -> CorrelationIdMiddleware -> FeatureFlagsMiddleware -> GeolocationMiddleware -> UserAgentMiddleware -> LoggingMiddleware. LoggingMiddleware depends on CorrelationId and Geolocation.
