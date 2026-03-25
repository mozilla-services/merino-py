# Flight Status Provider

Handles flight status queries from the Firefox address bar. If the sanitized query matches a flight number in a GCS-sourced manifest, respond with flight details from a Redis cache, or live AeroAPI (FlightAware) calls on cache miss. This provider is fronted by a circuit breaker.

## Request Flow

```mermaid
sequenceDiagram
    actor Firefox
    participant Merino
    participant GCS
    participant Redis
    participant AeroAPI as AeroAPI (FlightAware)

    Firefox->>Merino: GET /api/v1/suggest?q=ac 100

    alt Flight number not in manifest
        Merino-->>Firefox: { suggestions: [] }
    else Flight number in manifest
        Merino->>Redis: Look up flight status

        alt Cached
            Redis-->>Merino: Flight data
        else Not cached
            Redis-->>Merino: (miss)
            Merino->>AeroAPI: GET /flights/AC100
            AeroAPI-->>Merino: Flight data
            Merino->>Redis: Store flight data
        end

        Merino-->>Firefox: { suggestions: [{provider: "flightaware", ...}] }
    end
```

## Flight Numbers Manifest Sync

Flight numbers are loaded into memory from GCS on app startup and refreshed periodically (see [config](../operations/configs.md#general)). This is an append-only manifest which contains all flight numbers that have been synced via the scheduled flight numbers ingestion job.

```mermaid
sequenceDiagram
    participant Merino
    participant GCS

    Note over Merino: App startup
    Merino->>GCS: Fetch flight number manifest
    GCS-->>Merino: list of valid flight numbers
    Note over Merino: Stores manifest in memory

    loop Periodic refresh
        Merino->>GCS: Fetch flight number manifest
        GCS-->>Merino: list of valid flight numbers
        Note over Merino: Updates in-memory manifest
    end
```

## Flight Numbers Ingestion Job (Manifest update)

This ingest job fetches flight numbers for scheduled flights from AeroAPI every 6 hours, and adds them to the existing flight numbers manifest(s) in GCS. Currently two copies of the manifests are stored in separate buckets as part of ongoing GCP v2 migration.

The job scheduling and invocation is handled by Airflow (see [dags](https://github.com/mozilla/telemetry-airflow/blob/main/dags/merino_jobs.py) here).

```mermaid
sequenceDiagram
    participant Job as fetch_flights Job
    participant AeroAPI as AeroAPI (FlightAware)
    participant GCS

    loop Every 6 hours
        Job->>AeroAPI: GET scheduled flights
        AeroAPI-->>Job: Page of scheduled flights
    end

    Job->>GCS: Download existing flight_numbers_latest.json
    GCS-->>Job: Existing flight number list

    Note over Job: Merge new + existing (union)

    Job->>GCS: Upload flight_numbers_latest.json (×2 buckets)
```

Note that the job can be configured to store the manifest in Redis by setting `settings.flightaware.storage` (resolves to `MERINO_FLIGHTAWARE__STORAGE` env var) to `redis`. However, the provider is only configured to fetch the manifest from GCS.
