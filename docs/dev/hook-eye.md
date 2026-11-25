# Hook-eye: additional monitoring

Hook-eye (`apps/hook-eye`, package `merino-hook-eye`) is a small service for monitoring that
Merino's application metrics, traces, and OpenTelemetry Collector receivers can't cover. A
check belongs in hook-eye when:

- it can't come from Merino's own metrics or an existing OpenTelemetry Collector receiver;
- it polls a single shared resource, where one poller is correct and one per Merino pod would
  multiply load and duplicate series;
- or it needs privileges that Merino's pods shouldn't have.

Its only check today is the [cross-cluster replication (CCR) monitor](#ccr-monitor).

## How it works

Hook-eye has no API. Its FastAPI app serves only the Dockerflow endpoints (`/__heartbeat__`,
`/__lbheartbeat__`, `/__version__`) for Kubernetes probes, and its lifespan runs each enabled
check on a `merino_common.utils.cron.Job`.

Each check has its own settings section, named after the check, with an `enabled` switch, so
one image can run different checks per deployment. For example, a deployment in the leader
region disables the CCR follower check, since there's no follower there to scrape:

```sh
MERINO_HOOK_EYE_CCR_FOLLOWER__ENABLED=false
```

`/__heartbeat__` returns 503 when an enabled check's loop has died or hasn't finished a run in
three intervals, so point the liveness probe at it to restart a wedged monitor. Failed runs still
count as progress: an unreachable target is reported by the check's run counter, not by a
restart.

It runs as its own single-replica deployment, with its own image (`merino-hook-eye`) published
to Merino's artifact registry by the main workflow, tagged both `latest` and with the short
commit SHA (e.g. `merino-hook-eye:sha-1a2b3c4d5`). Because every replica would run every
check, extra replicas report duplicate series.

Checks follow the same reporting pattern:

- **Snapshot, then observe.** Each run replaces an in-memory snapshot, and the check's metrics
  are observable instruments that report from that snapshot whenever the OpenTelemetry SDK
  collects. Observable counters can export a source's running totals as-is, which synchronous
  counters can't.
- **Missing means unknown.** When a run fails, the snapshot is dropped, so stale values are
  never reported as current. Series also disappear when the thing they describe goes away.
  Alerts should treat a missing series as unhealthy.
- **Report the monitor's own health.** Each check counts its runs by outcome (for CCR,
  `merino.ccr.scrape{status=...}`), so a broken monitor can be told apart from a broken target.

The code only uses the OpenTelemetry API. In deployed environments the OpenTelemetry Kubernetes
operator supplies the SDK and exporter; without one, every instrument is a no-op.

Every metric, its labels, and what it indicates is documented in
[`apps/hook-eye/metrics.yaml`](https://github.com/mozilla-services/merino-py/blob/main/apps/hook-eye/metrics.yaml).

## Configuration

Settings live in `apps/hook-eye/merino_hook_eye/configs/*.toml`, selected by
`MERINO_HOOK_EYE_ENV` (development, testing, stage, production), and can be overridden with
`MERINO_HOOK_EYE_{SECTION}__{KEY}` environment variables. The shared sections are
`[logging]` (`format`, `level`, `can_propagate`) and `[sentry]` (`mode`, `dsn`, `env`,
`traces_sample_rate`); each check adds its own sections. See `default.toml` for every setting
and its default.

## CCR monitor

Merino's follower Elasticsearch clusters replicate the wikipedia and sports indices from the
leader in us-west1. The CCR monitor reads
[`GET _ccr/stats`](https://www.elastic.co/guide/en/elasticsearch/reference/8.18/ccr-get-stats.html)
on a follower every minute and emits leading-indicator metrics for:

- **Connectivity and discovery**, from `auto_follow_stats`: failed remote cluster state
  requests, failed follow indices, and the time since each remote cluster was last checked.
- **Per-shard replication**, from `follow_stats`, for the wikipedia and sports follower
  indices: leader and follower global checkpoints, aliases and settings versions, the time
  since the last read from the leader, and failed reads.

It meets all three criteria above: the stock `elasticsearch` receiver doesn't read
`_ccr/stats`; the endpoint needs the `monitor` cluster privilege, which Merino's pods don't
have; and the stats are local to the follower, so one reader per follower is enough. Deploy
one hook-eye per follower cluster.

### CCR settings

All in the `[ccr_follower]` section:

| Setting                              | Env var                                             | Default                    |
| ------------------------------------ | --------------------------------------------------- | -------------------------- |
| Run the check                        | `MERINO_HOOK_EYE_CCR_FOLLOWER__ENABLED`             | `true`                     |
| Follower URL                         | `MERINO_HOOK_EYE_CCR_FOLLOWER__URL`                 | `http://localhost:9201`    |
| API key (`monitor` privilege)        | `MERINO_HOOK_EYE_CCR_FOLLOWER__API_KEY`             | empty (no auth)            |
| Request timeout, seconds             | `MERINO_HOOK_EYE_CCR_FOLLOWER__REQUEST_TIMEOUT_SEC` | `10.0`                     |
| Scrape interval, seconds             | `MERINO_HOOK_EYE_CCR_FOLLOWER__INTERVAL_SEC`        | `60` (`15` in development) |
| Follower indices to report per shard | `MERINO_HOOK_EYE_CCR_FOLLOWER__INDEX_PATTERNS`      | `["*wiki-*", "*sports-*"]` |

The follower URL and API key are set per deployment in stage and production. Only follower
indices matching `index_patterns` get per-shard series, which bounds label cardinality.

### End-to-end test locally

This runs hook-eye against a real leader and follower and follows its metrics through the
OpenTelemetry Collector into Prometheus and Grafana, using the services in
`dev/docker-compose.yaml`:

| Service          | Port | Role                                                  |
| ---------------- | ---- | ----------------------------------------------------- |
| `es01`           | 9200 | Leader cluster                                        |
| `es02`           | 9201 | Follower cluster (`ccr` profile), read by hook-eye    |
| `es-ccr-setup`   |      | One-off: trial licenses, remote `leader`, auto-follow |
| `otel-collector` | 4318 | OTLP receiver; Prometheus exporter on 9464            |
| `prometheus`     | 9090 | Scrapes the collector every 5 seconds                 |
| `grafana`        | 3000 | Prometheus datasource preprovisioned, anonymous admin |

You need Docker running and dependencies installed (`make install`). Run everything from the
repository root. The steps use this shorthand for the Compose command:

```sh
dc() { docker compose --env-file dev/.env -f dev/docker-compose.yaml --profile ccr "$@"; }
```

#### 1. Start the clusters and the OpenTelemetry stack

```sh
make docker-compose-up-ccr
```

This starts every local service. To start only what this test needs (Tempo comes along as a
dependency of the collector):

```sh
dc up -d es01 es02 es-ccr-setup otel-collector prometheus grafana
```

Wait for the CCR setup to finish, then check that the follower is connected to the leader:

```sh
dc logs es-ccr-setup | tail -3
# ... --- Done ---
curl -s "http://localhost:9201/_remote/info?pretty"
# "leader": { "connected": true, ... }
```

The setup moves both clusters onto a 30-day trial license, which CCR requires. If it fails
because a trial was already used, see
[Cross-cluster replication (CCR)](./dependencies.md#cross-cluster-replication-ccr).

#### 2. Create followed indices on the leader

Auto-follow only picks up leader indices matching `*wiki-*` or `*sports-*` that are created
after the pattern exists. Create one of each, for example by running the wikipedia indexer
against `http://localhost:9200`, or by hand:

```sh
for index in enwiki-local-1 sports-local-1; do
  curl -s -X PUT "http://localhost:9200/$index" > /dev/null
  curl -s -X POST "http://localhost:9200/$index/_doc?refresh=true" \
    -H "Content-Type: application/json" -d '{"title": "test"}' > /dev/null
done

# A few seconds later, both are followed:
curl -s "http://localhost:9201/_cat/indices/*-local-1?v"
curl -s "http://localhost:9201/_ccr/stats?pretty"
```

#### 3. Run hook-eye with metrics export

```sh
make dev-hook-eye-otel
```

`opentelemetry-instrument` stands in for the Kubernetes operator: it configures the SDK and
exports over OTLP to the collector on `localhost:4318` every 15 seconds. The development
config scrapes every 15 seconds and logs each scrape at debug level. In another terminal:

```sh
curl -i localhost:8002/__heartbeat__   # 200
```

#### 4. Check the collector and Prometheus

The collector re-exposes everything it receives on its Prometheus endpoint. Use it to find
the exact metric names: dots become underscores, counters get a `_total` suffix, and units
may add a suffix too.

```sh
curl -s localhost:9464/metrics | grep '^merino_ccr'
```

At <http://localhost:9090/targets>, the `otelcol` target should be up. Series appear within
about 30 seconds of hook-eye starting: one scrape, one export, one Prometheus scrape.

Locally, series take longer to disappear than they will in deployed environments. The
collector's Prometheus exporter keeps serving a series' last value for 5 minutes after it
stops arriving (its default `metric_expiration`), so wherever a step below says series
disappear, expect them to flatline for up to 5 minutes first. Hook-eye itself stops
exporting them immediately.

#### 5. Query in Grafana

Open <http://localhost:3000> (no login), go to **Explore**, keep the default **Prometheus**
datasource, and try:

```promql
merino_ccr_scrape_total
merino_ccr_follower_global_checkpoint
merino_ccr_leader_global_checkpoint - merino_ccr_follower_global_checkpoint
rate(merino_ccr_failed_read_requests_total[5m])
rate(merino_ccr_auto_follow_failed_remote_cluster_state_requests_total[5m])
```

Per-shard series are labelled `remote_cluster`, `index`, and `shard`. There should be one for
shard 0 of each of `enwiki-local-1` and `sports-local-1`. There's no hook-eye dashboard yet,
so build panels in Explore.

#### 6. Exercise the failure modes

- **Replication in progress.** Index a batch of documents on the leader and watch
  `leader - follower` checkpoint go up briefly and back to 0:

  ```sh
  for i in $(seq 1 500); do
    curl -s -X POST "http://localhost:9200/sports-local-1/_doc" \
      -H "Content-Type: application/json" -d "{\"n\": $i}" > /dev/null
  done
  ```

- **Paused follower index.** Pausing removes the index's shard-follow tasks, so its series
  disappear from `_ccr/stats` and from the metrics. Resume it to bring them back:

  ```sh
  curl -X POST "http://localhost:9201/enwiki-local-1/_ccr/pause_follow"
  curl -X POST "http://localhost:9201/enwiki-local-1/_ccr/resume_follow"
  ```

- **Follower unreachable.** Stop the follower: every CCR series disappears and
  `merino_ccr_scrape_total{status="error"}` climbs. `/__heartbeat__` stays 200, because
  failed scrapes are hook-eye working correctly against a broken target.

  ```sh
  dc stop es02
  dc start es02
  ```

- **Leader unreachable.** Stop the leader: hook-eye keeps scraping the follower, and the
  follower's attempts to reach the leader should show up as climbing
  `failed_read_requests` and `failed_remote_cluster_state_requests`, and as growing
  `time_since_last_read_ms` and `time_since_last_check_ms`.

  ```sh
  dc stop es01
  dc start es01
  ```

- **Monitor stopped.** Stop hook-eye with Ctrl-C: the series stop updating, and disappear
  once the collector expires them.

#### 7. Clean up

```sh
make docker-compose-down     # keeps the volumes, and the trial license with them
make docker-compose-down-v   # also deletes the data, which allows a fresh trial
```

To run hook-eye without the collector, `make dev-hook-eye` skips `opentelemetry-instrument`.
Every instrument is then a no-op, but the scrape logs still show it working.

## Adding a check

Each check is a subpackage of `merino_hook_eye`, like `merino_hook_eye/ccr/`. To add one:

1. Confirm it meets the criteria above. If an OpenTelemetry Collector receiver or an application's own
   metrics can cover it, use those instead.
2. Put the new check in its own subpackage, following the CCR check's snapshot, observe,
   and run-outcome pattern. Create its instruments with the shared
   `merino_hook_eye.metrics.meter`.
3. Give the check a `start()` async context manager that wraps one run in
   `merino_hook_eye.checks.run_check`, as `merino_hook_eye/ccr/follower.py` does. That gives
   it its own cron loop, so one check's failures or slow runs don't hold up another's, and
   covers it in `/__heartbeat__`.
4. Register `start` in `CHECKS` in `merino_hook_eye/app.py`, keyed by the check's name. Give
   the check a `[default.<name>]` section in `default.toml` holding `enabled` and all its
   other settings, with validators, and override them in per-environment files as needed.
5. Document its metrics under a new group in `apps/hook-eye/metrics.yaml`, with a
   `merino.<check>.` prefix.
6. Add unit tests under `apps/hook-eye/tests/unit/<check>/`, and a section to this page on
   running and verifying it locally.

Any credentials it needs should grant only what the check reads, as the CCR monitor's API key
only has the `monitor` privilege.

## Test, lint, and build

```sh
moon run hook-eye:unit-test
moon run hook-eye:lint hook-eye:format-check hook-eye:typecheck hook-eye:security
moon run hook-eye:docker-build   # app-hook-eye:build
```
