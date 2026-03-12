# Corpus Cache (Redis L2)

Shared Redis cache between the per-pod in-memory cache and the Corpus GraphQL API.

## Why

Merino pods each independently fetch from the Corpus API on a short interval. This puts unnecessary load on Apollo/Client-API and creates risk as we expand internationally or scale pod count.

## How it works

```mermaid
flowchart TB
    req["Firefox NewTab Request"]

    subgraph L1 ["L1 — Per-Pod In-Memory SWR"]
        check_l1{{"Check in-memory cache"}}
    end

    respond_fresh["Respond with fresh data"]
    respond_stale["Respond with stale data"]

    subgraph bg ["Background Revalidation Task"]
        direction TB

        subgraph L2 ["L2 — Shared Redis"]
            check_l2{{"Check Redis cache"}}
            acquire_lock{{"Try distributed lock"}}
        end

        api["Fetch from Corpus GraphQL API"]
        write["Write to Redis + release lock + update L1"]
    end

    req --> check_l1

    check_l1 -- "FRESH HIT" --> respond_fresh
    check_l1 -- "STALE" --> respond_stale
    check_l1 -. "MISS (cold start, blocks)" .-> check_l2

    respond_stale -. "spawns task" .-> check_l2

    check_l2 -- "FRESH HIT" --> done_l2["Update L1 cache"]
    check_l2 -. "STALE" .-> acquire_lock
    check_l2 -. "MISS" .-> acquire_lock

    acquire_lock -- "LOCK ACQUIRED" --> api
    acquire_lock -. "LOCK HELD + stale exists" .-> serve_stale["Return stale data"]
    acquire_lock -. "LOCK HELD + no data" .-> retry["Wait, retry Redis, or raise"]

    api --> write --> done_api["Update L1 cache"]

    style req fill:#2c3e50,stroke:#1a252f,color:#ecf0f1,stroke-width:2px
    style check_l1 fill:#2980b9,stroke:#1f6da0,color:#fff,stroke-width:2px
    style check_l2 fill:#d35400,stroke:#a04000,color:#fff,stroke-width:2px
    style acquire_lock fill:#e67e22,stroke:#bf6516,color:#fff,stroke-width:2px
    style api fill:#1e8449,stroke:#145a32,color:#fff,stroke-width:2px
    style write fill:#1e8449,stroke:#145a32,color:#fff,stroke-width:2px
    style respond_fresh fill:#27ae60,stroke:#1e8449,color:#fff,stroke-width:2px
    style respond_stale fill:#27ae60,stroke:#1e8449,color:#fff,stroke-width:2px
    style serve_stale fill:#f4d03f,stroke:#d4ac0f,color:#333
    style retry fill:#e74c3c,stroke:#c0392b,color:#fff
    style done_l2 fill:#27ae60,stroke:#1e8449,color:#fff
    style done_api fill:#27ae60,stroke:#1e8449,color:#fff
    style L1 fill:#eaf2f8,stroke:#2980b9,stroke-width:2px,color:#2c3e50
    style L2 fill:#fef5e7,stroke:#d35400,stroke-width:2px,color:#2c3e50
    style bg fill:#f4f6f7,stroke:#95a5a6,stroke-width:2px,stroke-dasharray: 8 4,color:#2c3e50
```

Two layers of caching sit in front of the Corpus GraphQL API:

- **L1 (in-memory SWR)** — per-pod. Serves requests immediately. On stale, spawns a background task to revalidate.
- **L2 (Redis)** — shared across all pods. The background task checks Redis before hitting the API.

When L2 is stale, one pod acquires a distributed lock, fetches from the API, and writes to Redis. Other pods serve stale data until the winner finishes.

On cold start (no L1 or L2 data), the request blocks until data is fetched. All pods may hit the API simultaneously in this case — same as today without the cache.

## Configuration

Config section: `[default.curated_recommendations.corpus_cache]` in `merino/configs/default.toml`.

Key settings:
- `cache` — `"redis"` to enable, `"none"` to disable (default: disabled)
- `soft_ttl_sec` — when a cached entry is considered stale and triggers revalidation
- `hard_ttl_sec` — when Redis evicts the key entirely (safety net)
- `lock_ttl_sec` — auto-release timeout if the lock holder crashes
- `key_prefix` — bump the version on schema changes to avoid deserialization errors

Env var override pattern: `MERINO__CURATED_RECOMMENDATIONS__CORPUS_CACHE__CACHE=redis`

Uses the shared Redis cluster (`[default.redis]`). No separate instance needed.

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Cache layer | Redis L2 behind existing in-memory L1 | Keeps per-pod latency low, Redis only consulted on L1 miss |
| Write pattern | Distributed stale-while-revalidate | One pod revalidates, others serve stale. Avoids thundering herd |
| Lock mechanism | `SET NX EX` with TTL | Simple, self-expiring. Worst case on timeout: one extra API call |
| Cache format | Pydantic model dicts via orjson | Saves CPU across pods vs re-parsing raw GraphQL |
| Failure mode | All Redis errors fall through to API | Redis is an optimization, never a requirement |

## Rollout

1. Deploy with cache disabled (no behavior change)
2. Enable in staging
3. Monitor metrics, validate API call reduction
4. Enable in production

## Key files

- `merino/curated_recommendations/corpus_backends/redis_cache.py` — cache logic
- `merino/curated_recommendations/__init__.py` — wiring (`_init_corpus_cache`)
- `merino/configs/default.toml` — config section with defaults and documentation
